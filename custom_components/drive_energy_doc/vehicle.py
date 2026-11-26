"""Ein Fahrzeug: Zustand, Tankerkennung, Preis, Beleg-Dialog und Speicherung."""

from __future__ import annotations

import asyncio
import csv
import json
import re
import io
import logging
import time
import uuid
from datetime import datetime, time as dtime, timedelta
from pathlib import Path
from typing import Any

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later, async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from . import channels as chan
from . import charge, curve, messages, receipt, stats, wallbox
from .const import *  # noqa: F403
from .detector import FuelDetector
from .price import lookup, resolve_provider
from . import whatsapp
from .telegram import get_bot

_LOGGER = logging.getLogger(__name__)
CHECK_EVERY = timedelta(seconds=15)
AWAIT_TTL = 6 * 3600
OPEN_WINDOW = 6 * 3600        # ein zuletzt angelegter Eintrag ohne Beleg bzw. ohne Kilometerstand bleibt so lange "offen"
REMIND_AFTER = 30 * 60       # nach so vielen Sekunden wird an einen fehlenden Beleg erinnert
CSV_FIELDS = ["fahrzeug", "kennzeichen", "art", "bezeichnung", "datum", "uhrzeit", "km", "ort", "adresse", "breitengrad", "laengengrad", "von_prozent", "bis_prozent", "menge", "einheit", "preis_pro_einheit", "betrag_eur", "quelle_menge", "quelle_preis", "beleg", "verbrauch_pro_100km", "notiz"]


def default_ai_entity(hass: HomeAssistant) -> str | None:
    from homeassistant.helpers import entity_registry as er

    ents = [e for e in er.async_get(hass).entities.values() if e.domain == "ai_task" and not e.disabled]
    for e in ents:
        if e.platform == "google_generative_ai_conversation":
            return e.entity_id
    return ents[0].entity_id if ents else None


def get_settings(hass: HomeAssistant) -> dict:
    """Globale Einstellungen (Preisquellen, Strompreis, KI), für alle Fahrzeuge gleich."""
    for e in hass.config_entries.async_entries(DOMAIN):
        if e.data.get(CONF_KIND) == KIND_SETTINGS:
            return {**e.data, **e.options}
    return {}


def signal(entry_id: str) -> str:
    return f"{DOMAIN}_update_{entry_id}"


PANEL_SIGNAL = f"{DOMAIN}_panel"   # Ereignisse für die offene Panel-Seite (Websocket drive_energy_doc/subscribe)


class Vehicle:
    def __init__(self, hass: HomeAssistant, entry) -> None:
        self.hass, self.entry = hass, entry
        o = {**entry.data, **entry.options}
        self.o = o
        self.name: str = o[CONF_NAME]
        self.image_file: str = str(o.get(CONF_IMAGE_FILE) or "")
        self.plate: str = str(o.get(CONF_PLATE) or "").upper().strip()
        self.energy: str = o[CONF_ENERGY]
        self.electric = self.energy == ENERGY_ELECTRIC
        self.unit = "kWh" if self.electric else "l"
        self.phev = bool(o.get(CONF_PHEV)) and not self.electric   # Plug-in-Hybrid: Kraftstoff (l) und Strom (kWh) in einer Liste
        self.capacity = float(o.get(CONF_CAPACITY) or 0)
        self.store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")
        self.data: dict[str, Any] = {"entries": [], "pending": None, "pending_el": None, "awaiting": None}
        self.detector = FuelDetector(
            min_increase=float(o.get(CONF_MIN_INCREASE, DEFAULT_MIN_INCREASE)),
            settle_seconds=float(o.get(CONF_SETTLE) or (DEFAULT_SETTLE_ELECTRIC if self.electric else DEFAULT_SETTLE_FUEL)),
            min_distance=float(o.get(CONF_MIN_DISTANCE, DEFAULT_MIN_DISTANCE)),
            require_distance=bool(o.get(CONF_REQUIRE_DISTANCE, not self.electric)),
            reject_moving=self.electric,   # Elektroauto: Anstieg während der Fahrt ist Rekuperation
        )
        self.capacity_el = float(o.get(CONF_CAPACITY_EL) or 0)
        # Plug-in-Hybrid: zweite Erkennung für den Akku (Laden), mit den Werten eines Elektroautos (kein Abstand zum Ladeort nötig)
        self.detector_el: FuelDetector | None = FuelDetector(
            min_increase=float(o.get(CONF_MIN_INCREASE, DEFAULT_MIN_INCREASE)),
            settle_seconds=float(o.get(CONF_SETTLE) or DEFAULT_SETTLE_ELECTRIC),
            require_distance=False,
            reject_moving=True,   # Anstieg des Akkus beim Fahren (Rekuperation) ist kein Laden
        ) if self.phev and o.get(CONF_LEVEL_EL) else None
        self._wb = wallbox.Log()   # Verlauf der Heim-Wallbox (nur im Speicher)
        self._wb_run: tuple[float, float] | None = None   # (Beginn, Zählerstand), seit die Wallbox liefert
        self._wb_idle_since: float | None = None
        self._curve: list[list] = []   # Ladekurve der laufenden Ladung (ein Punkt pro Minute)
        self._curve_saved = 0.0
        self.curve_dir = Path(hass.config.path(DOMAIN, entry.entry_id, "curves"))
        self._pos: tuple[float, float] | None = None
        self._exif_pos: tuple[float, float] | None = None   # Aufnahmeort des Fotos, das gerade gelesen wird (Foto-Metadaten)
        self._capture: list[str] | None = None
        self._upload_lock = asyncio.Lock()
        self.last_extra_id: str | None = None
        self.last_entry_id: str | None = None   # zuletzt durch einen Upload angelegter oder geänderter Eintrag (das Panel springt in der Liste dorthin)
        self._batch: set[str] | None = None   # Stapel-Upload aus dem Panel: Plausibilitätsprüfung erst am Ende (batch_finish)
        self._unsubs: list = []
        self.photo_dir = Path(hass.config.path(DOMAIN, entry.entry_id, "photos"))
        self.orig_dir = Path(hass.config.path(DOMAIN, entry.entry_id, "originals"))
        self.media_dir = Path((hass.config.media_dirs or {}).get("local") or hass.config.path("media"))

    # ---------------------------------------------------------------- Lebenszyklus
    async def async_setup(self) -> None:
        saved = await self.store.async_load() or {}
        self.data.update(saved)
        await self.hass.async_add_executor_job(self._import_folder)   # Erstimport (leeres Fahrzeug) oder Neuimport (Datei REPLACE im Importordner)
        self.detector.pending = FuelDetector(pending=self.data.get("pending")).pending
        wr = self.data.get("wb_run")
        self._wb_run = (float(wr[0]), float(wr[1])) if wr else None
        running = self.curve_dir / "running.json"
        if self._wb_run or self.data.get("pending") or self.data.get("pending_el"):
            self._curve = curve.restore(await self.hass.async_add_executor_job(curve.read, running))
        for x in self.data.get("wb_log") or []:   # Wallbox-Verlauf wiederherstellen (Beginn einer Ladung bleibt berechenbar)
            try:
                self._wb.s.append((float(x[0]), float(x[1]), None if x[2] is None else float(x[2])))
            except (TypeError, ValueError, IndexError):
                pass
        if self.detector_el:
            self.detector_el.pending = FuelDetector(pending=self.data.get("pending_el")).pending
        o = self.o
        for e in self.data["entries"]:
            if e.get("quantity_source") == "import" and "increase" not in e and e.get("level_to") is not None:
                # Import aus der alten Tabelle: dort war „%“ der Zuwachs beim Tanken, nicht der Füllstand danach
                e["increase"] = e["level_to"]
                e["level_from"] = e["level_to"] = None
            if e.get("kind") == "adblue":  # frühere Fassung: AdBlue wurde zum allgemeinen Zubehör
                e.update(kind="extra", item="AdBlue", unit="l")
        if self.data.get("awaiting_adblue"):
            self.data["awaiting_extra"] = self.data.pop("awaiting_adblue")
        for e in self.data["entries"]:   # frühere Fassungen haben Belegnummern o. ä. als Kilometerstand übernommen: unmögliche, nicht von Hand gesetzte Stände entfernen
            if e.get("odometer") is not None and e.get("odometer_source") not in ("manuell", "sensor") and e.get("kind") != "extra" and not self._km_sane(e["odometer"], e["id"]):
                _LOGGER.info("Unmöglicher Kilometerstand %s im Eintrag %s entfernt (%s)", e["odometer"], e["id"], self.name)
                e["odometer"] = None
                e["odometer_source"] = None
        if self.data.get("photos_v", 0) < 1:   # einmalig (auch nach einem Neuimport): sprechende Dateinamen und kleinere Dateien für schon vorhandene Fotos
            try:
                await self.hass.async_add_executor_job(self._migrate_photos)
            except Exception as err:  # noqa: BLE001 - die Fotos bleiben dann unverändert
                _LOGGER.warning("Foto-Migration übersprungen: %r", err)
        self._save()
        if await self.hass.async_add_executor_job(self._rescan_marker().is_file):   # Datei config/drive_energy_doc/rescan/<Fahrzeugname>: alle Fotos mit der KI neu einlesen und neu ablegen (einmalig, kurz nach dem Start)
            @callback
            def _start_rescan(_now) -> None:   # als callback markiert: läuft im Event-Loop (ein Lambda würde im Thread-Pool laufen)
                self.hass.async_create_task(self.rescan_photos())

            self._unsubs.append(async_call_later(self.hass, 90, _start_rescan))
        self._pos = self._read_pos()
        lvl = self._read_float(o.get(CONF_LEVEL))
        if lvl is not None:
            self.detector.prev_level = lvl
        if self.detector_el:
            lvl_el = self._read_float(o.get(CONF_LEVEL_EL))
            if lvl_el is not None:
                self.detector_el.prev_level = lvl_el
        for d, v in ((self.detector, lvl), (self.detector_el, self._read_float(o.get(CONF_LEVEL_EL)) if self.detector_el else None)):
            if d and d.pending and d.pending.valid and v is not None and v > d.pending.level:
                d.pending.level = v   # während des Neustarts weitergeladen: Endstand nachziehen (sonst fehlt der Zuwachs in der Schätzung)
        tracked = [e for e in (o.get(CONF_LEVEL), o.get(CONF_LEVEL_EL) if self.detector_el else None, o.get(CONF_TRACKER), o.get(CONF_POWER), o.get(CONF_CHARGE_TYPE), o.get(CONF_WB_ENERGY), o.get(CONF_WB_POWER), o.get(CONF_PLUG)) if e]
        self._wb_sample()
        self._unsubs.append(async_call_later(self.hass, 25, self._recover_wb_run))   # Beginn einer laufenden Wallbox-Lieferung aus dem Verlauf holen (Neustart, Neukonfigurieren)
        self._unsubs.append(async_track_state_change_event(self.hass, tracked, self._state_changed))
        self._unsubs.append(async_track_time_interval(self.hass, self._tick, CHECK_EVERY))
        if o.get(CONF_TG_TOKEN) and o.get(CONF_TG_CHAT) and o.get(CONF_CH_ON["telegram"], True):
            get_bot(self.hass, o[CONF_TG_TOKEN]).add(o[CONF_TG_CHAT], self.handle_message)
        if o.get(CONF_WA_PHONE) and o.get(CONF_CH_ON["whatsapp"], True):
            whatsapp.hub(self.hass)["routes"][whatsapp.norm_phone(o[CONF_WA_PHONE])] = self

    def _migrate_photos(self) -> None:
        """Einmalig (Executor): schon abgelegte Fotos in sprechende Namen umbenennen (Datei in photos/ und originals/ sowie der Eintrag) und größere Dateien stärker komprimieren."""
        import re as _re

        keep = {(self.data.get("unread_photo") or {}).get("name")}
        renamed = shrunk = 0
        for e in self.data["entries"]:
            names = e.get("photos") or []
            for i, n in enumerate(names):
                if not isinstance(n, str) or _re.match(r"\d{4}-\d\d-\d\d_\d{4}_", n) or n in keep or not (self.photo_dir / n).is_file():
                    continue
                if i:
                    label = "Zusatzfoto"
                elif e.get("kind") == "extra":
                    label = e.get("item") or "Zubehoer"
                else:
                    label = "Tanken" if e.get("receipt") else "Foto"
                new = receipt.new_photo_name({"station": e.get("station")}, e.get("ts"), label, self.photo_dir)
                try:
                    (self.photo_dir / n).rename(self.photo_dir / new)
                    if (self.orig_dir / n).is_file():
                        (self.orig_dir / n).rename(self.orig_dir / new)
                except OSError as err:
                    _LOGGER.warning("Foto %s nicht umbenannt: %r", n, err)
                    continue
                names[i] = new
                renamed += 1
        for folder, side, q, limit in ((self.photo_dir, 1400, 80, 250_000), (self.orig_dir, 1800, 82, 400_000)):
            if not folder.is_dir():
                continue
            for f in folder.iterdir():
                if f.suffix.lower() == ".jpg" and f.stat().st_size > limit:
                    old = f.read_bytes()
                    new = receipt.recompress(old, side, q)
                    if len(new) < 0.8 * len(old):
                        f.write_bytes(new)
                        shrunk += 1
        self.data["photos_v"] = 1
        _LOGGER.info("%s: %d Fotos umbenannt, %d verkleinert", self.name, renamed, shrunk)

    def _rescan_marker(self) -> Path:
        return Path(self.hass.config.path(DOMAIN, "rescan", self.name))

    def _import_folder(self) -> None:
        """Import: config/drive_energy_doc/import/<Fahrzeugname>/entries.json (+ photos/, originals/). Läuft im Executor.
        Nur bei leerem Fahrzeug, es sei denn, im Ordner liegt eine Datei REPLACE: dann werden die vorhandenen Einträge und Fotos
        zuerst nach config/drive_energy_doc/backup/<Fahrzeugname>_<Zeit>/ gesichert (verschoben, nichts wird gelöscht) und durch den Import ersetzt."""
        import json
        import shutil

        src = Path(self.hass.config.path(DOMAIN, "import", self.name))
        f = src / "entries.json"
        if not f.is_file():
            return
        replace = (src / "REPLACE").is_file()
        if self.data["entries"] and not replace:
            return
        if replace:
            bk = Path(self.hass.config.path(DOMAIN, "backup", f"{self.name}_{datetime.now():%Y%m%d_%H%M%S}"))
            bk.mkdir(parents=True, exist_ok=True)
            (bk / "entries.json").write_text(json.dumps(self.data["entries"], ensure_ascii=False, indent=1), encoding="utf-8")
            for d in (self.photo_dir, self.orig_dir):
                if d.is_dir():
                    shutil.move(str(d), str(bk / d.name))
            self.data["photos_v"] = 0   # Fotos des Imports danach in die neue Namensform bringen
            _LOGGER.info("%s: vorhandene Einträge und Fotos gesichert nach %s", self.name, bk)
        self.data["entries"] = json.loads(f.read_text(encoding="utf-8"))
        for sub, dst in (("photos", self.photo_dir), ("originals", self.orig_dir)):
            if (src / sub).is_dir():
                dst.mkdir(parents=True, exist_ok=True)
                for p in (src / sub).iterdir():
                    shutil.copy2(p, dst / p.name)
        done = src.with_name(src.name + ".done")
        shutil.rmtree(done, ignore_errors=True)
        src.rename(done)
        _LOGGER.info("%s: %d Einträge importiert", self.name, len(self.data["entries"]))

    async def rescan_photos(self) -> None:
        """Jedes Foto aus ``originals/`` mit der KI neu einlesen, sauber zuschneiden und mit sprechendem Namen neu ablegen. Werte, die der Eintrag schon hat,
        bleiben unverändert (Abweichungen stehen im Bericht config/drive_energy_doc/rescan_<Fahrzeug>_<Zeit>.csv); fehlende Werte werden ergänzt."""
        marker = self._rescan_marker()
        rows = ["Datum;Foto alt;Foto neu;Status;Hinweis"]
        async with self._upload_lock:
            for e in list(self.data["entries"]):
                for i, n in enumerate(list(e.get("photos") or [])):
                    when = dt_util.as_local(dt_util.utc_from_timestamp(e["ts"])).strftime("%d.%m.%Y %H:%M")
                    if not receipt.safe_photo_name(n):
                        rows.append(f"{when};{n};;ungültiger Name, übersprungen;")
                        continue
                    src = await self.hass.async_add_executor_job(lambda n=n: next((p for p in (self.orig_dir / n, self.photo_dir / n) if p.is_file()), None))
                    if src is None:
                        rows.append(f"{when};{n};;Datei fehlt;")
                        continue
                    image = await self.hass.async_add_executor_job(lambda p=src: receipt.normalize(p.read_bytes()))
                    ai = await receipt.ai_read(self.hass, self._ai_entity(), image, self.media_dir, self._pos, self._exif_pos)
                    if ai and ai.get("busy"):
                        rows.append(f"{when};{n};;KI überlastet, unverändert;")
                        _LOGGER.warning("Foto-Neueinlesen: KI überlastet, Foto %s bleibt unverändert", n)
                        continue
                    if ai and ai.get("error"):
                        rows.append(f"{when};{n};;KI hat abgelehnt ({ai['error']}), unverändert;")
                        _LOGGER.warning("Foto-Neueinlesen: KI hat die Anfrage abgelehnt (%s), Foto %s bleibt unverändert", ai["error"], n)
                        continue
                    note = []
                    info = None
                    if ai:
                        info = {**ai, "station": ai.get("station") or e.get("station")}
                        for k, lab in (("quantity", "Menge"), ("total", "Betrag")):
                            if ai.get(k) and e.get(k) and abs(ai[k] - e[k]) > 0.02:
                                note.append(f"{lab} Foto {ai[k]} / Eintrag {e[k]}")
                            elif ai.get(k) and not e.get(k) and e.get("kind") != "extra":
                                e[k] = ai[k]
                                note.append(f"{lab} ergänzt {ai[k]}")
                        if ai.get("unit_price") and not e.get("unit_price") and e.get("kind") != "extra":
                            e["unit_price"] = ai["unit_price"]
                        if ai.get("odometer") and self._km_sane(ai["odometer"], e.get("id")) and stats.km_better(e, "foto" if not (ai.get("quantity") or ai.get("total")) else "beleg"):
                            e["odometer"], e["odometer_source"] = float(ai["odometer"]), "foto" if not (ai.get("quantity") or ai.get("total")) else "beleg"
                            note.append(f"km ergänzt {ai['odometer']:.0f}")
                        for k in ("station", "address"):
                            if ai.get(k) and not e.get(k):
                                e[k] = ai[k]
                                note.append(f"{k} ergänzt")
                    label = "Zusatzfoto" if i else None
                    if e.get("kind") == "extra" and not (info or {}).get("category"):
                        label = label or e.get("item") or "Zubehoer"
                    new = await self.hass.async_add_executor_job(receipt.save_new_photo, image, (ai or {}).get("crop"), self.photo_dir, info or {"station": e.get("station")}, e["ts"], label, self.orig_dir)
                    await self._remove_files([n])
                    e["photos"][i] = new
                    rows.append(f"{when};{n};{new};{'gelesen' if ai else 'KI ohne Ergebnis, nur neu abgelegt'};{' | '.join(note)}")
                    self._save()
            self._notify_entities()
        rep = Path(self.hass.config.path(DOMAIN, f"rescan_{self.name}_{datetime.now():%Y%m%d_%H%M%S}.csv"))
        await self.hass.async_add_executor_job(lambda: (rep.write_text("\n".join(rows) + "\n", encoding="utf-8-sig"), marker.unlink(missing_ok=True)))
        _LOGGER.info("%s: %d Fotos neu eingelesen, Bericht %s", self.name, len(rows) - 1, rep)

    async def async_unload(self) -> None:
        if self._curve:
            await self.hass.async_add_executor_job(curve.write, self.curve_dir / "running.json", [list(x) for x in self._curve])
        for u in self._unsubs:
            u()
        self._unsubs.clear()
        if self.o.get(CONF_TG_TOKEN) and self.o.get(CONF_TG_CHAT):
            get_bot(self.hass, self.o[CONF_TG_TOKEN]).remove(self.o[CONF_TG_CHAT])
        if self.o.get(CONF_WA_PHONE):
            whatsapp.hub(self.hass)["routes"].pop(whatsapp.norm_phone(self.o[CONF_WA_PHONE]), None)

    # ---------------------------------------------------------------- Zustände lesen
    def _read_float(self, entity_id: str | None) -> float | None:
        st = self.hass.states.get(entity_id) if entity_id else None
        if st is None or st.state in ("unknown", "unavailable", ""):
            return None
        try:
            return float(st.state)
        except ValueError:
            return None

    def _read_pos(self) -> tuple[float, float] | None:
        st = self.hass.states.get(self.o.get(CONF_TRACKER) or "")
        if st is None:
            return None
        lat, lon = st.attributes.get("latitude"), st.attributes.get("longitude")
        return (float(lat), float(lon)) if lat is not None and lon is not None else self._pos

    @callback
    def _state_changed(self, event: Event) -> None:
        entity = event.data["entity_id"]
        if entity == self.o.get(CONF_TRACKER):
            self._pos = self._read_pos()
            self._tick(None)
            return
        if entity == self.o.get(CONF_PLUG) and entity not in (self.o.get(CONF_LEVEL), self.o.get(CONF_LEVEL_EL)):
            self._tick(None)   # abgesteckt: die Ladung kann abgeschlossen werden
            return
        if entity in (self.o.get(CONF_WB_ENERGY), self.o.get(CONF_WB_POWER)) and entity not in (self.o.get(CONF_LEVEL), self.o.get(CONF_LEVEL_EL)):
            self._wb_sample()   # Verlauf der Heim-Wallbox mitschreiben
            return
        if entity in (self.o.get(CONF_POWER), self.o.get(CONF_CHARGE_TYPE)) and entity not in (self.o.get(CONF_LEVEL), self.o.get(CONF_LEVEL_EL)):
            self._sample_charge()   # Ladeleistung und Ladeart des Autos während des Ladens
            return
        level = self._read_float(entity)
        if level is None:
            return
        det = self.detector_el if (self.detector_el and entity == self.o.get(CONF_LEVEL_EL)) else self.detector   # Akku (Laden) oder Tank
        result = det.on_level(level, time.time(), self._pos, self._read_float(self.o.get(CONF_ODOMETER)))
        if result in ("started", "valid", "cancelled"):
            self._save()
        if result in ("started", "valid"):
            self._sample_charge()
        elif det.pending and det.pending.valid and det is self._charge_det():
            self._panel("changed", live=True)   # laufende Ladung: nur die türkise Zeile im Panel nachführen
        if result == "valid":
            self.hass.async_create_task(self._fetch_price(None, det))
            home = det is self._charge_det() and self._wb_run is not None   # die eigene Wallbox liefert gerade: Heimladung, keine Säule zum Fotografieren
            if self._push_at_start(det) and not home:
                self.hass.async_create_task(self._push_started(det))
        self._notify_entities()

    def _detected_text(self, entry: dict) -> str:
        """Meldung nach dem Abschluss eines erkannten Tank- oder Ladevorgangs: Zusammenfassung und die Bitte um den Beleg."""
        return self._summary(entry, self.tr("Tankvorgang erkannt")) + "\n\n" + self.tr("Bitte schick mir den Beleg (Foto vom Bon oder der Zapfsäule) oder tippe: Menge Betrag, z. B. 45,93 105,13") + "\n" + self.tr("Zubehör gekauft (AdBlue, Öl, Scheibenwischer …)? Schreib: extra 24,90 oder x Öl 1 9,50 (auch als Bildtext zum Foto). Alle Kommandos: ? oder hilfe.")

    async def simulate_refuel(self, phase: str = "both", delay: int = 30, energy: str | None = None) -> list[str]:
        """Test für die Meldungen am Handy: schickt dieselben Nachrichten wie bei einem echten Vorgang (Beginn und/oder Abschluss) mit Beispielwerten. Es wird nichts gespeichert und keine Liste verändert;
        Kanäle, Push-Schalter, Zeitpunkt und Link gelten wie im Betrieb. Rückgabe: was gesendet wurde."""
        el = (energy == "electric") if energy else self.electric
        det = self.detector_el if (el and self.detector_el) else self.detector
        sent: list[str] = []
        if phase in ("start", "both"):
            if self._push_at_start(det):
                await self._say("🧪 " + self.tr("{0}: Tanken bzw. Laden läuft. Fotografiere jetzt die Anzeige an der Säule (Menge und Preis), solange du noch dort bist. Den Beleg kannst du danach schicken.", self.name), quick=True, phase="start", el=el)
                sent.append("start")
            else:
                _LOGGER.info("Simulation (%s): Push am Beginn ist laut Einstellung „Zeitpunkt“ ausgeschaltet", self.name)
            if phase == "both" and delay > 0:
                await asyncio.sleep(delay)
        if phase in ("end", "both"):
            km = next((x.get("odometer") for x in reversed(self.data["entries"]) if x.get("odometer") is not None), None)
            sample = {"ts": time.time(), "kind": None, "energy": "electric" if el else None, "station": self.tr("Teststation"), "address": None, "odometer": km, "quantity": 12.5 if el else 40.0,
                      "quantity_source": "sensor", "unit_price": 0.45 if el else 1.859, "price_source": "sensor", "total": 5.63 if el else 74.36, "note": "", "level_from": 20.0, "level_to": 70.0}
            await self._say("🧪 " + self._detected_text(sample), quick=True, phase="end", el=el)
            sent.append("end")
        return sent

    def _phase_for(self, ch: str, el: bool) -> str | None:
        """Wann bekommt dieser Kanal die Meldung zum Vorgang? „start“, „end“ oder None (keine). Einstellung je Kanal: auto = Kraftstoff am Beginn, Strom (Laden) am Ende."""
        mode = self.o.get(CONF_TIMING_ON[ch]) or "auto"
        if mode == "none":
            return None
        if mode == "auto":
            return "end" if el else "start"
        return mode

    def _push_at_start(self, det: FuelDetector) -> bool:
        """Meldung schon beim Beginn des Vorgangs? Ja, wenn mindestens ein Kanal sie am Beginn bekommen soll."""
        el = self.electric or det is self.detector_el
        return any(self._phase_for(ch, el) == "start" for ch in self.channels() if self.o.get(CONF_DETECT_ON[ch], True))

    async def _push_started(self, det: FuelDetector) -> None:
        """Sobald das Tanken oder Laden läuft (Füllstand steigt deutlich): gleich Bescheid geben, solange man noch an der Säule steht. Das Foto der Anzeige, das jetzt kommt, wird beim Abschluss dem Vorgang zugeordnet."""
        p = det.pending
        if not p or p.extras.get("started_push") or p.extras.get("receipt"):
            return
        p.extras["started_push"] = True
        self._save()
        await self._say(self.tr("{0}: Tanken bzw. Laden läuft. Fotografiere jetzt die Anzeige an der Säule (Menge und Preis), solange du noch dort bist. Den Beleg kannst du danach schicken.", self.name), quick=True, phase="start", el=self.electric or det is self.detector_el)

    @callback
    def _tick(self, _now) -> None:
        self._pos = self._read_pos() or self._pos
        self._wb_sample()
        self._sample_charge()
        self._curve_sample()
        finished = False
        plugged, odo = self._plugged(), self._read_float(self.o.get(CONF_ODOMETER))
        for det in self._detectors():
            done = det.check(time.time(), self._pos, odo, plugged if det is self._charge_det() else None)
            if done:
                finished = True
                self.hass.async_create_task(self._finish(done, det is self.detector_el))
        if not finished:
            self._notify_entities()
            if self.live() and time.time() - getattr(self, "_live_ts", 0) >= 60:
                self._live_ts = time.time()
                self.store.async_delay_save(self._store_data, 30)   # laufenden Vorgang regelmäßig sichern (Absturz, Stromausfall)
                self._panel("changed", live=True)   # laufende Ladung: Zeile im Panel jede Minute nachführen

    def _car_power_w(self) -> float | None:
        pe = self.o.get(CONF_POWER)
        w = self._read_float(pe) if pe else None
        if w is None:
            return None
        st = self.hass.states.get(pe)
        return w * 1000 if str((st.attributes.get("unit_of_measurement") if st else "") or "").lower() == "kw" else w

    def _curve_sample(self) -> None:
        """Ladekurve: während einer Ladung einmal pro Minute Leistung (Wallbox, Auto) und Ladestand merken; in Pausen seltener."""
        now = time.time()
        if not self.live():
            if self._curve and self._wb_run is None and not any(d.pending for d in self._detectors()):
                self._curve = []   # keine Ladung (Anstieg verworfen): Kurve verwerfen
                self.hass.async_add_executor_job(lambda: (self.curve_dir / "running.json").unlink(missing_ok=True))
            return
        wb = self._wb.s[-1][2] if (self.o.get(CONF_WB_POWER) and self._wb.s) else None
        if wb is not None and self._read_float(self.o.get(CONF_WB_POWER)) is None:
            wb = None   # Sensor kurz nicht verfügbar (z. B. 7 s beim Wiederverbinden): Lücke statt eines falschen Einbruchs auf 0
        car = self._car_power_w()
        soc = self._read_float(self.o.get(CONF_LEVEL_EL if self.detector_el else CONF_LEVEL))
        if curve.skip_idle(self._curve, now, wb, car, soc):
            return
        if curve.add(self._curve, now, wb, car, soc) and now - self._curve_saved > 300:
            self._curve_saved = now
            pts = [list(x) for x in self._curve]
            self.hass.async_add_executor_job(curve.write, self.curve_dir / "running.json", pts)   # übersteht einen Neustart

    async def load_curve(self, entry_id: str) -> dict | None:
        """Gespeicherte Ladekurve eines Eintrags (für das Panel); „live“ = Kurve der laufenden Ladung."""
        if entry_id == "live":
            return curve.payload(self._curve) if self._curve else None
        if not self.get_entry(entry_id):
            return None
        return await self.hass.async_add_executor_job(curve.read, self.curve_dir / f"{entry_id}.json")

    def _plugged(self) -> bool | None:
        """Stecker-Sensor: True angesteckt, False abgesteckt, None ohne Sensor oder unbekannt."""
        e = self.o.get(CONF_PLUG)
        st = self.hass.states.get(e) if e else None
        return wallbox.parse_plug(st.state) if st else None

    def _wb_sample(self) -> None:
        """Zählerstand und Leistung der Heim-Wallbox in den Verlauf schreiben."""
        ee = self.o.get(CONF_WB_ENERGY)
        if not ee:
            return
        kwh = self._read_float(ee)
        st = self.hass.states.get(ee)
        if kwh is not None:
            kwh = wallbox.to_kwh(kwh, st.attributes.get("unit_of_measurement") if st else None)
        pe = self.o.get(CONF_WB_POWER)
        w = self._read_float(pe)
        if w is not None:
            ps = self.hass.states.get(pe)
            w = wallbox.to_watt(w, ps.attributes.get("unit_of_measurement") if ps else None)
        elif pe and (self.hass.states.get(pe) is None or self.hass.states.get(pe).state in ("unavailable", "unknown")):
            w = 0.0   # Wallbox stromlos oder abgeschaltet: der letzte Leistungswert bleibt nicht stehen
        self._wb.add(time.time(), kwh, w)
        now = time.time()
        if w is not None and w >= wallbox.IDLE_WATT:   # die Wallbox liefert: Beginn merken, solange das Auto noch keinen Anstieg meldet
            self._wb_idle_since = None
            if self._wb_run is None and kwh is not None:
                self._wb_run = (now, kwh)
        elif w is not None and self._wb_run is not None:
            self._wb_idle_since = self._wb_idle_since or now
            if now - self._wb_idle_since > 900:
                self._wb_run = None

    async def _recover_wb_run(self, _now=None) -> None:
        """Beim Start: lieferte die Wallbox schon vor dem Start, den Beginn und den Zählerstand davor aus dem Recorder holen (der Speicher kennt nur die Zeit seit dem Start)."""
        pe, ee = self.o.get(CONF_WB_POWER), self.o.get(CONF_WB_ENERGY)
        cur = self._wb.s[-1] if self._wb.s else None
        if not (pe and ee) or not cur or not cur[2] or cur[2] < wallbox.IDLE_WATT:
            return
        try:
            from functools import partial

            from homeassistant.components.recorder import get_instance, history

            end = dt_util.utcnow()
            res = await get_instance(self.hass).async_add_executor_job(partial(
                history.get_significant_states, self.hass, end - timedelta(hours=12), end, [pe, ee],
                include_start_time_state=True, significant_changes_only=False, no_attributes=False))
        except Exception as err:  # noqa: BLE001 - ohne Verlauf bleibt der Beginn der Zeitpunkt des Starts
            _LOGGER.debug("Wallbox-Verlauf nicht lesbar (%s): %r", self.name, err)
            return
        power: list[tuple[float, float]] = []
        energy: list[tuple[float, float]] = []
        for s in res.get(pe, []):
            try:
                power.append((s.last_updated.timestamp(), wallbox.to_watt(float(s.state), s.attributes.get("unit_of_measurement"))))
            except (TypeError, ValueError):
                power.append((s.last_updated.timestamp(), 0.0))   # nicht verfügbar: Wallbox stromlos
        for s in res.get(ee, []):
            try:
                energy.append((s.last_updated.timestamp(), wallbox.to_kwh(float(s.state), s.attributes.get("unit_of_measurement"))))
            except (TypeError, ValueError):
                pass
        run = wallbox.find_run(power, energy)
        if run and (self._wb_run is None or run[0] < self._wb_run[0]):
            self._wb_run = run
            self._save(panel=False)
            self._panel("changed", live=True)

    def _wb_price_now(self) -> float | None:
        raw = self.o.get(CONF_WB_PRICE)
        if not raw:
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            return self._read_float(str(raw))

    def _wb_match(self, done: dict, est: float | None) -> tuple[float | None, str | None]:
        """Energie der Heim-Wallbox für diese Ladung: (kWh, None) oder (None, Grund), wenn sie nicht zugeordnet werden kann."""
        self._wb_sample()
        ex = done.get("extras") or {}
        now = time.time()
        stored = ex.get("wb_end") if ex.get("wb_base") is not None else None   # während der Ladung mitgeschrieben: gilt auch über lange Pausen und einen Neustart
        end = stored[0] if stored else min(now, done["last_increase_ts"] + max(self.detector.settle_seconds, 900))
        others: list[dict] = []
        for v in self.hass.data.get(DOMAIN, {}).get("vehicles", {}).values():   # dieselbe Wallbox bei einem anderen Fahrzeug: nicht raten, wenn die Zeiten sich überlappen
            if v is self or v.o.get(CONF_WB_ENERGY) != self.o.get(CONF_WB_ENERGY):
                continue
            others += [{"ts_start": x.get("ts_start"), "ts": x.get("ts")} for x in v.data["entries"][-30:] if x.get("kind") != "extra"]
            d = v._charge_det()
            if d and d.pending:
                others.append({"ts_start": d.pending.start_ts, "ts": now})
        if wallbox.shared_conflict(done["start_ts"], end, others):
            return None, "geteilt"
        kwh = round(stored[1] - ex["wb_base"], 3) if stored and stored[1] >= ex["wb_base"] else self._wb.energy(done["start_ts"], end)
        if kwh is None:
            return None, "kein Verlauf"
        if not wallbox.plausible(kwh, est):
            return None, "passt nicht"
        return kwh, None

    def _charge_det(self) -> FuelDetector | None:
        """Erkennung, die das Laden (Strom) verfolgt: bei Elektroauto die einzige, beim Plug-in-Hybrid die für den Akku."""
        return self.detector_el if self.detector_el else (self.detector if self.electric else None)

    def _ac_max(self) -> float | None:
        try:
            return float(self.o.get(CONF_AC_MAX)) if self.o.get(CONF_AC_MAX) else None
        except (TypeError, ValueError):
            return None

    def _sample_charge(self) -> None:
        """Während eines Ladevorgangs die Spitzenleistung und die Ladeart des Autos merken (steht beim Abschluss nicht mehr zur Verfügung)."""
        det = self._charge_det()
        p = det.pending if det else None
        if not p:
            return
        ex = p.extras
        if self.o.get(CONF_WB_ENERGY) and self._wb.s:
            if ex.get("wb_base") is None:
                b = self._wb_run[1] if (self._wb_run and self._wb_run[0] <= p.start_ts + 60) else self._wb.baseline(p.start_ts)
                if b is not None:
                    ex["wb_base"] = b
                    self._save(panel=False)
            cur = self._wb.s[-1]
            now = time.time()
            if cur[2] is not None:
                if "wb_on_s" not in ex:   # Lieferung lief schon vor dem ersten Anstieg des Ladestands: diese Zeit zählt mit
                    ex["wb_on_s"] = round(max(0.0, p.start_ts - self._wb_run[0]) if (self._wb_run and self._wb_run[0] <= p.start_ts) else 0.0)
                if cur[2] >= wallbox.IDLE_WATT:
                    ex["wb_peak_w"] = round(max(cur[2], ex.get("wb_peak_w") or 0))
                    if ex.get("wb_on_last"):
                        ex["wb_on_s"] = round(ex["wb_on_s"] + min(now - ex["wb_on_last"], 120))   # aktive Ladezeit ohne Pausen
                ex["wb_on_last"] = now
            if ex.get("wb_base") is not None and cur[1] is not None and ex.get("rise_lvl") != p.level:
                # Wallbox-Zähler, als das Auto diesen Ladestand meldete (für den vorläufigen Verlust); beim ersten Mal (z. B. nach einem Neustart) ist der Meldezeitpunkt unbekannt: auf die nächste Meldung warten
                ex["rise_kwh"] = cur[1] if "rise_lvl" in ex else None
                ex["rise_lvl"] = p.level
            if ex.get("wb_base") is not None and cur[1] > (ex.get("wb_end") or [0, ex["wb_base"]])[1]:
                ex["wb_end"] = [cur[0], cur[1]]   # letzter Zählerstand, bei dem die Wallbox noch geliefert hat
                if time.time() - getattr(self, "_wb_saved", 0) > 300:
                    self._wb_saved = time.time()
                    self._save(panel=False)
        pe = self.o.get(CONF_POWER)
        if pe:
            w = self._read_float(pe)
            st = self.hass.states.get(pe)
            if w is not None:
                if str((st.attributes.get("unit_of_measurement") if st else "") or "").lower() == "kw":
                    w *= 1000
                if w > (ex.get("peak_w") or 0):
                    ex["peak_w"] = round(w)
        if self.o.get(CONF_WB_PRICE):   # Preis der Wallbox über die Ladung mitteln (Mischpreis ändert sich mit der Sonne)
            pr = self._wb_price_now()
            if pr is not None:
                ex["wbp_sum"] = round(ex.get("wbp_sum", 0) + pr, 4)
                ex["wbp_n"] = ex.get("wbp_n", 0) + 1
        se = self.o.get(CONF_WB_SOLAR)
        if se:   # Solaranteil der Ladung über die Zeit mitteln
            sv = self._read_float(se)
            if sv is not None:
                ex["wbs_sum"] = round(ex.get("wbs_sum", 0) + sv, 2)
                ex["wbs_n"] = ex.get("wbs_n", 0) + 1
        te = self.o.get(CONF_CHARGE_TYPE)
        if te:
            st = self.hass.states.get(te)
            t = charge.parse_type(st.state if st else None)
            if t and (t == "dc" or ex.get("ctype") is None) and ex.get("ctype") != t:
                ex["ctype"] = t   # DC gewinnt: ein später gemeldetes AC überschreibt es nicht
                self._save(panel=False)

    def live(self) -> dict | None:
        """Laufende Ladung (gültiger Anstieg, noch nicht abgeschlossen) für die türkise Zeile im Panel."""
        det = self._charge_det()
        p = det.pending if det else None
        if not p or not p.valid:
            return self._live_provisional(det)
        cap = self.capacity_el if self.detector_el else self.capacity
        est = round((p.level - p.start_level) / 100 * cap, 2) if cap else None
        ex = p.extras
        kwh = round(ex["wb_end"][1] - ex["wb_base"], 3) if (ex.get("wb_base") is not None and ex.get("wb_end")) else (self._wb.energy(p.start_ts, time.time()) if self.o.get(CONF_WB_ENERGY) else None)
        w = self._wb.s[-1][2] if (self.o.get(CONF_WB_POWER) and self._wb.s) else None
        if w is not None and w < wallbox.IDLE_WATT:
            w = None
        paused = time.time() - p.last_increase_ts > max(det.settle_seconds, 300) and not w
        out = {"ts_start": p.start_ts, "level_from": round(p.start_level, 1), "level_to": round(p.level, 1), "est_quantity": est, "wb_kwh": kwh if (kwh and kwh > 0) else None, "kw": round(w / 1000, 1) if w else None, "paused": paused}
        on = ex.get("wb_on_s")
        if out["wb_kwh"] and on and on >= 600:
            out["avg_kw"] = round(out["wb_kwh"] / (on / 3600), 1)   # wie beim Abschluss: Wallbox-Energie durch aktive Ladezeit
        else:
            av = charge.avg_power_kw(est, p.start_ts, p.last_increase_ts, p.level - p.start_level)
            out["avg_kw"] = round(av, 1) if av else None
        out["charge_type"] = self._live_ctype(ex) if self.o.get(CONF_CHARGE_TYPE) else charge.classify(None, ex.get("peak_w"), charge.avg_power_kw(est, p.start_ts, p.last_increase_ts, p.level - p.start_level), self._ac_max())[0]
        self._live_money(out, ex, p.odometer, est)
        stable = not w and time.time() - p.last_increase_ts >= 600   # Wallbox liefert nicht und der Ladestand blieb 10 Minuten gleich: das Auto ist nachgekommen, sonst täuscht der Verzug der Audi-Cloud einen hohen Verlust vor
        if out["wb_kwh"] and est and est >= 2 and stable:
            out["loss_pct"] = round((out["wb_kwh"] / est - 1) * 100)   # Ladeverlust: Wallbox-Energie gegenüber dem, was im Akku ankam
        elif est and est >= 3 and ex.get("rise_kwh") is not None and ex.get("wb_base") is not None and ex.get("rise_lvl") == p.level:
            # während der Ladung: Wallbox-Energie bis zur letzten Meldung des Ladestands gegen die Schätzung (der Verzug der Auto-Cloud kürzt sich weitgehend heraus)
            out["loss_pct"] = round(((ex["rise_kwh"] - ex["wb_base"]) / est - 1) * 100)
            out["loss_prov"] = True
        return out

    async def finish_charge(self) -> bool:
        """Laufende Ladung von Hand abschließen (Knopf „Ladung abschließen“): Eintrag wie beim Wegfahren; eine weitere Lieferung der Wallbox beginnt eine neue Ladung."""
        det = self._charge_det()
        done = det.finish_now() if det else None
        if not done:
            return False
        self._wb_run = None   # Beginn der Wallbox-Lieferung vergessen: liefert die Wallbox weiter, zählt das als neue Ladung
        await self._finish(done, det is self.detector_el)
        return True

    def _live_ctype(self, ex: dict) -> str | None:
        """Ladeart der laufenden Ladung aus der Ladeart-Entität des Autos: der während der Ladung gemerkte Wert (DC gewinnt), sonst der aktuelle Zustand."""
        if ex.get("ctype"):
            return ex["ctype"]
        st = self.hass.states.get(self.o.get(CONF_CHARGE_TYPE))
        return charge.parse_type(st.state if st else None)

    def _live_money(self, out: dict, ex: dict, odometer: float | None, est: float | None) -> None:
        """Kilometerstand, Preis und Betrag der laufenden Ladung (vorläufig: mittlerer Preis bisher, sonst aktueller Preis)."""
        out["odometer"] = odometer if odometer is not None else self._read_float(self.o.get(CONF_ODOMETER))
        n = ex.get("wbp_n")
        price = (ex["wbp_sum"] / n) if n else (self._wb_price_now() if out.get("wb_kwh") else None) or self._electric_price()
        out["unit_price"] = round(price, 4) if price else None
        q = out.get("wb_kwh") if out.get("wb_kwh") is not None else est
        out["total"] = round(q * price, 2) if (q and price) else None

    def _live_provisional(self, det) -> dict | None:
        """Die Wallbox liefert, das Auto hat aber noch keinen Anstieg gemeldet (der Ladestand kommt oft erst nach Minuten): Zeile schon jetzt anzeigen."""
        if det is None or not self.o.get(CONF_WB_POWER) or self._wb_run is None or not self._wb.s:
            return None
        if self._plugged() is False:
            return None
        if self._plugged() is not True:   # ohne Stecker-Sensor nur, wenn kein anderes Fahrzeug dieselbe Wallbox mitbenutzt
            ent = self.o.get(CONF_WB_ENERGY)
            if any(v is not self and v.o.get(CONF_WB_ENERGY) == ent for v in self.hass.data.get(DOMAIN, {}).get("vehicles", {}).values()):
                return None
        start, base = self._wb_run
        cur = self._wb.s[-1]
        w = cur[2] if cur[2] and cur[2] >= wallbox.IDLE_WATT else None
        kwh = round(cur[1] - base, 3) if cur[1] >= base else None
        cand = det.pending   # Anstieg noch unter der Schwelle: Kandidat mit Start- und aktuellem Stand
        lvl = self._read_float(self.o.get(CONF_LEVEL_EL if self.detector_el else CONF_LEVEL))
        out = {"ts_start": start, "level_from": round(cand.start_level, 1) if cand else None, "level_to": round(cand.level, 1) if cand else (round(lvl, 1) if lvl is not None else None), "est_quantity": None, "wb_kwh": kwh if kwh and kwh > 0 else None, "kw": round(w / 1000, 1) if w else None, "paused": False, "provisional": True,
               "avg_kw": round(kwh / ((time.time() - start) / 3600), 1) if (kwh and kwh > 0 and time.time() - start >= 600) else None}
        out["charge_type"] = self._live_ctype({}) if self.o.get(CONF_CHARGE_TYPE) else (charge.classify(None, w, None, self._ac_max())[0] if w else None)
        self._live_money(out, {}, None, None)
        return out

    def correction(self) -> dict:
        """Korrekturfaktoren (Beleg geteilt durch Schätzung) je Energieart und Ladeart für die Anzeige im Panel."""
        out: dict[str, Any] = {}
        kinds = [("electric", self.capacity if self.electric else self.capacity_el)] if (self.electric or self.phev) else []
        if not self.electric:
            kinds.append(("fuel", self.capacity))
        for kind, cap in kinds:
            row = {}
            for ct in (None, "ac", "dc"):
                f, n, _ = charge.factor(self.data["entries"], kind, cap, ct)
                if ct is None or charge.samples(self.data["entries"], kind, cap, ct):
                    row[ct or "all"] = {"factor": f, "n": len(charge.samples(self.data["entries"], kind, cap, ct))}
            out[kind] = row
        return out

    def _detectors(self) -> list[FuelDetector]:
        return [self.detector] + ([self.detector_el] if self.detector_el else [])

    def _pending_for(self, energy: str | None):
        """Laufender Vorgang zur Energieart (Plug-in-Hybrid: Laden oder Tanken), sonst der des Fahrzeugs."""
        return self.detector_el.pending if (energy == "electric" and self.detector_el) else self.detector.pending

    def _valid_pending(self):
        """Der gerade laufende (gültige) Tank- oder Ladevorgang oder None."""
        return next((d.pending for d in self._detectors() if d.pending and d.pending.valid), None)

    def _ai_entity(self) -> str | None:
        """Gewählte KI-Aufgabe, sonst automatisch Gemini, sonst die erste vorhandene ai_task-Entität."""
        cfg = get_settings(self.hass).get(CONF_AI_TASK)
        if cfg:
            from homeassistant.helpers import entity_registry as er

            if er.async_get(self.hass).async_get(cfg) is None:   # die gewählte KI-Aufgabe gibt es nicht mehr (z. B. nach dem Wechsel von Gemini zu Claude)
                _LOGGER.warning("Die gewählte KI-Aufgabe %s existiert nicht mehr, es wird %s verwendet", cfg, default_ai_entity(self.hass))
                cfg = None
        return cfg or default_ai_entity(self.hass)

    # ---------------------------------------------------------------- Preis
    async def _fetch_price(self, pending: dict | None = None, det: FuelDetector | None = None) -> dict[str, Any]:
        """Preis/Station für den laufenden Vorgang holen (am Beginn gültiger Zuwachs, nicht erst beim Wegfahren)."""
        det = det or self.detector
        p = det.pending
        target = p.extras if p else (pending or {})
        if self.electric or (self.detector_el is not None and det is self.detector_el):
            price = self._electric_price()
            if price:
                target.update(unit_price=price, price_source="eingestellt")
        else:
            cfg = get_settings(self.hass)
            key = cfg.get(CONF_TK_KEY)
            prov = resolve_provider(cfg.get(CONF_PRICE_PROVIDER), self.hass.config.country, key)
            lat, lon = (p.lat, p.lon) if p else (pending or {}).get("pos", (None, None))
            if prov and lat is not None:
                st = await lookup(async_get_clientsession(self.hass), prov, key, lat, lon, self.energy)
                if st:
                    target.update(station=st["station"], address=st["address"], station_id=st["station_id"], unit_price=st["unit_price"], price_source=prov)
        self._save()
        return target

    def _electric_price(self) -> float | None:
        raw = get_settings(self.hass).get(CONF_EL_PRICE)
        if not raw:
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            return self._read_float(str(raw))

    # ---------------------------------------------------------------- Tankende
    async def _finish(self, done: dict, el: bool = False) -> None:
        ex = dict(done.get("extras") or {})
        if "unit_price" not in ex:
            ex = await self._fetch_price({**done, "pos": (done["lat"], done["lon"]), **ex}, self.detector_el if el else None) or ex
        pct = done["level"] - done["start_level"]
        cap = self.capacity_el if el else self.capacity   # Plug-in-Hybrid: Akku (kWh) oder Tank (l)
        est = round(pct / 100 * cap, 2) if cap else None   # Schätzung: Zuwachs mal Kapazität; sie bleibt am Eintrag, auch wenn ein Beleg die Menge ersetzt
        kind = "electric" if (el or self.electric) else "fuel"
        ctype = csrc = ckw = None
        if kind == "electric":
            ctype, csrc, ckw = charge.classify(ex.get("ctype"), ex.get("peak_w"), charge.avg_power_kw(est, done.get("start_ts"), done.get("last_increase_ts"), pct), self._ac_max())
        fac, _n, _grp = charge.factor(self.data["entries"], kind, cap, ctype)   # gelernter Korrekturfaktor aus Einträgen mit Beleg
        qty = round(est * fac, 2) if (est and fac) else est
        src = "berechnet (korrigiert)" if (est and fac) else "berechnet"
        wb, wb_note = (self._wb_match(done, est) if (kind == "electric" and self.o.get(CONF_WB_ENERGY)) else (None, None))
        if wb:
            qty, src = wb, "wallbox"   # gemessene Energie der Heim-Wallbox (einschließlich der Ladeverluste)
        entry = {
            "id": uuid.uuid4().hex[:12],
            "ts": done["last_increase_ts"],
            "ts_start": done["start_ts"],
            "odometer": done.get("odometer"),
            "odometer_source": "sensor" if done.get("odometer") is not None else None,
            "lat": done.get("lat"),
            "lon": done.get("lon"),
            "station": ex.get("station"),
            "address": ex.get("address"),
            "station_id": ex.get("station_id"),
            "level_from": round(done["start_level"], 1),
            "level_to": round(done["level"], 1),
            "quantity": qty,
            "quantity_source": src,
            "unit_price": ex.get("unit_price"),
            "price_source": ex.get("price_source"),
            "total": None,
            "photos": [],
            "receipt": False,
            "note": "",
        }
        if el:
            entry["energy"] = "electric"
        if est:
            entry["est_quantity"] = est
        if est and fac:
            entry["est_factor"] = fac
        if ctype:
            entry["charge_type"], entry["charge_src"] = ctype, csrc
        if ckw and kind == "electric":
            entry["charge_kw"] = ckw
        if kind == "electric":
            pk = ex.get("peak_w") or ex.get("wb_peak_w")   # Leistungssensor des Autos, sonst die Wallbox
            if pk:
                entry["peak_kw"] = round(pk / 1000, 1)
            on = ex.get("wb_on_s")
            if wb and on and on >= 600:
                entry["avg_kw"] = round(wb / (on / 3600), 1)   # gelieferte Energie durch aktive Ladezeit (Pausen zählen nicht)
            else:
                av = charge.avg_power_kw(qty, done.get("start_ts"), done.get("last_increase_ts"), pct)
                if av:
                    entry["avg_kw"] = round(av, 1)
        if wb:
            entry["wb_kwh"] = wb
            if ex.get("wbs_n"):
                entry["solar_pct"] = round(max(0.0, min(100.0, ex["wbs_sum"] / ex["wbs_n"])))
            n = ex.get("wbp_n")
            price = (ex["wbp_sum"] / n) if n else self._wb_price_now()
            if price:
                entry["unit_price"], entry["price_source"] = round(price, 4), "Wallbox"
        elif wb_note:
            entry["wb_note"] = wb_note   # Wallbox ist eingerichtet, aber die Menge wurde nicht übernommen (geteilt, kein Verlauf, passt nicht)
        entry["total"] = round(qty * entry["unit_price"], 2) if qty and entry["unit_price"] else None
        if kind == "electric" and self._curve:
            pts = curve.trim([x for x in self._curve if x[0] >= done["start_ts"] - 6 * 3600])
            self._curve = []
            if len(pts) >= 3:
                entry["curve"] = True
                await self.hass.async_add_executor_job(curve.write, self.curve_dir / f"{entry['id']}.json", pts)
            await self.hass.async_add_executor_job(lambda: (self.curve_dir / "running.json").unlink(missing_ok=True))
        entry["photos"].extend(ex.get("extra_photos", []))
        r = ex.get("receipt")
        if r:
            self._apply_values(entry, r["values"], r.get("photo"))
        od = ex.get("odometer")
        if od:
            if stats.km_better(entry, "foto"):   # der Sensor des Autos geht vor
                entry["odometer"], entry["odometer_source"] = float(od["km"]), "foto"
            if od.get("photo"):
                entry["photos"].append(od["photo"])
        self.data["entries"].append(entry)
        self.data["pending_el" if el else "pending"] = None
        self._save()
        self._notify_entities()
        self.hass.bus.async_fire(f"{DOMAIN}_refuel", {"vehicle": self.name, "entry": entry})
        if entry.get("quantity_source") == "wallbox":   # Heimladung: Menge von der eigenen Wallbox, es gibt keinen Beleg – nur kurz im Panel melden, keine Beleg-Bitte
            self._panel("reply", text=self._summary(entry, self.tr("Heimladung erfasst")), entry=entry["id"])
        elif not r:
            await self._say(self._detected_text(entry), quick=True, phase="end", el=el)   # Push mit Link: Antippen öffnet die Aufnahme

    # ---------------------------------------------------------------- Nachrichten
    def pending_answers(self) -> list[str]:
        """Offene Rückfrage (nicht abgelaufen) und die dazu passenden fertigen Antworten (yes/no/new) fürs Panel."""
        def live(k: str) -> dict | None:
            x = self.data.get(k)
            return x if x and time.time() - x["ts"] < AWAIT_TTL else None
        ao = live("awaiting_odo")
        if ao and ao.get("confirm") and ao.get("photo") and not live("awaiting_overwrite"):
            return ["yes", "new", "no"]   # Tacho-Foto: statt „trotzdem übernehmen“ auch „neuer Eintrag“
        if live("awaiting_overwrite") or (ao and ao.get("confirm")):
            return ["yes", "no"]
        if live("awaiting"):
            return ["new"]
        if ao:
            return ["no"]
        return ["km", "doc", "del"] if live("unread_photo") and self._batch is None else []   # im Stapel nicht mitten drin fragen

    async def upload(self, image: bytes | None, text: str, batch: bool = False, finish: bool = False) -> list[str]:
        """Beleg aus dem Panel (Handykamera). Antworten kommen als Liste zurück statt per Messenger."""
        async with self._upload_lock:   # nacheinander: sonst überschreiben sich die Antwortlisten zweier gleichzeitiger Uploads
            if finish:
                return self.batch_finish()
            self._batch = (self._batch if self._batch is not None else set()) if batch else None
            self.last_extra_id = self.last_entry_id = None
            return await self._upload_locked(image, text)

    def batch_finish(self) -> list[str]:
        """Ende eines Stapel-Uploads: jetzt, wo alle Fotos zugeordnet sind, die Einträge prüfen (Verbrauch) und Auffälligkeiten melden."""
        ids, self._batch = self._batch or set(), None
        out = []
        for e in sorted((x for x in (self.get_entry(i) for i in ids) if x), key=lambda x: x["ts"]):
            chk = self._check_cons(self.data["entries"], e, e["odometer"]) if e.get("odometer") is not None else None
            if chk and not chk["ok"]:
                when = dt_util.as_local(dt_util.utc_from_timestamp(e["ts"])).strftime("%d.%m.%Y")
                out.append(f"{when}: " + self.tr("⚠️ Verbrauch ungewöhnlich: {0} bei {1} km seit dem letzten Tanken (Durchschnitt {2}), bitte Kilometerstand prüfen.", self._cons_txt(chk["cons"], chk.get("energy")), self._fmt_km(chk["driven"]), self._cons_txt(chk["avg"], chk.get("energy"))))
        up = self.data.get("unread_photo")
        if up and time.time() - up["ts"] < AWAIT_TTL:   # im Stapel unlesbar gebliebenes Foto: am Ende melden statt mittendrin zu fragen
            out.append(self.tr("Auf dem Foto konnte ich weder Beleg noch Kilometerstand lesen. Schick den Kilometerstand als Text (z. B. „km 61240“) oder lege das Foto nur zur Dokumentation ab, oder lösche es."))
        return out

    async def _upload_locked(self, image: bytes | None, text: str) -> list[str]:
        self._capture = []
        try:
            if image:
                sent = None   # Aufnahmezeit aus dem Foto: so wird ein später hochgeladenes Tacho-Foto dem richtigen Tankvorgang zugeordnet
                self._exif_pos = await self.hass.async_add_executor_job(receipt.exif_gps, image)
                taken = await self.hass.async_add_executor_job(receipt.exif_time, image)
                if taken:
                    ts = dt_util.as_timestamp(taken.replace(tzinfo=dt_util.get_default_time_zone()))
                    if ts <= time.time() + 3600:
                        sent = ts
                await self.receive_photo(image, text, sent)
            elif text:
                await self.receive_text(text)
            replies = list(self._capture or [])
            _LOGGER.info("Upload aus dem Panel (%s): Bild %s Byte, Text %r, %d Antwort(en)", self.name, len(image) if image else 0, text[:40], len(replies))
            return replies
        except Exception:
            _LOGGER.exception("Upload aus dem Panel (%s) fehlgeschlagen", self.name)
            raise
        finally:
            self._capture = None

    def plate_country(self) -> str:
        c = str(self.o.get(CONF_PLATE_COUNTRY) or self.hass.config.country or "DE").upper()
        return c if c in PLATE_COUNTRIES else "DE"

    def vehicle_type(self) -> str:
        """Fahrzeugtyp: gewählter Text, sonst Hersteller und Modell des Geräts hinter dem Füllstandssensor."""
        from homeassistant.helpers import device_registry as dr
        from homeassistant.helpers import entity_registry as er

        if self.o.get(CONF_VEHICLE_TYPE):
            return str(self.o[CONF_VEHICLE_TYPE])
        src = er.async_get(self.hass).async_get(self.o.get(CONF_LEVEL) or "")
        dev = dr.async_get(self.hass).async_get(src.device_id) if src and src.device_id else None
        if not dev:
            return ""
        model = dev.model or ""
        make = dev.manufacturer or ""
        return model if make and model.lower().startswith(make.lower()) else f"{make} {model}".strip()

    def image_entity(self) -> str | None:
        """Fahrzeugbild: gewählte Entität, sonst eine image-Entität desselben Geräts wie der Füllstandssensor."""
        from homeassistant.helpers import entity_registry as er

        if self.o.get(CONF_IMAGE):
            return self.o[CONF_IMAGE]
        reg = er.async_get(self.hass)
        src = reg.async_get(self.o.get(CONF_LEVEL) or "")
        if src and src.device_id:
            for e in er.async_entries_for_device(reg, src.device_id):
                if e.domain == "image" and not e.disabled:
                    return e.entity_id
        return None

    def channels(self) -> list[str]:
        """Eingerichtete Kanäle dieses Fahrzeugs, WhatsApp zuerst."""
        enabled = get_settings(self.hass).get(CONF_CHANNELS)  # Hauptschalter in den Einstellungen; ohne Angabe sind alle erlaubt
        on = lambda ch: self.o.get(CONF_CH_ON[ch], True)  # noqa: E731   Schalter je Fahrzeug
        out = []
        if self.o.get(CONF_WA_PHONE) and on("whatsapp") and (not enabled or "whatsapp" in enabled):
            out.append("whatsapp")
        if self.o.get(CONF_TG_TOKEN) and self.o.get(CONF_TG_CHAT) and on("telegram") and (not enabled or "telegram" in enabled):
            out.append("telegram")
        if self.o.get(CONF_NOTIFY) and on("companion") and (not enabled or "companion" in enabled):
            out.append("companion")
        return out

    async def send_channel(self, channel: str, text: str, quick: bool = False) -> tuple[bool, str]:
        return await chan.send(self.hass, self.name, self.entry.entry_id, self.o, get_settings(self.hass), channel, text, quick)

    async def test_channel(self, channel: str) -> tuple[bool, str]:
        if channel not in self.channels():
            return False, self.tr("Dieser Kanal ist bei diesem Fahrzeug nicht eingerichtet")
        label = {"whatsapp": "WhatsApp", "telegram": "Telegram", "companion": self.tr("die Companion-App")}[channel]
        return await self.send_channel(channel, self.tr("✅ Testnachricht von Drive Energy Doc ({0}): {1} funktioniert.", self.name, label))

    async def _say(self, text: str, quick: bool = False, phase: str | None = None, el: bool = False) -> None:
        if self._capture is not None:
            self._capture.append(text)
            return
        self._panel("reply", text=text, entry=self.last_entry_id)   # das Panel zeigt dieselbe Meldung wie der Bot im Chat
        for ch in self.channels():
            if quick:
                when = self._phase_for(ch, el)
                if not self.o.get(CONF_DETECT_ON[ch], True) or when is None or (phase and when != phase):
                    continue   # Meldung bei erkanntem Tankvorgang und Beleg-Erinnerung ist für diesen Kanal aus oder kommt zu einem anderen Zeitpunkt
            await self.send_channel(ch, text, quick)

    def _summary(self, e: dict, head: str) -> str:
        when = dt_util.as_local(dt_util.utc_from_timestamp(e["ts"])).strftime("%d.%m.%Y %H:%M")
        extra = e.get("kind") == "extra"
        unit = (e.get("unit") or "") if extra else self.unit_of(e)
        lines = [f"{'🧰' if extra else '⛽'} {self.name}{f' ({self.plate})' if self.plate else ''}: {head} ({when})"]
        if e.get("station") or e.get("address"):
            lines.append(" ".join(x for x in (e.get("station"), e.get("address")) if x))
        if e.get("odometer") is not None:
            lines.append(f"{e['odometer']:.0f} km")
        q = self._dec(f"{e['quantity']:.2f} {unit}".strip()) if e.get("quantity") else "?"
        lv = f"{e['level_from']:.0f} → {e['level_to']:.0f} %, " if e.get("level_from") is not None and e.get("level_to") is not None else ""
        if e.get("quantity") or not extra:
            lines.append(f"{q} ({lv}{self.tr(e['quantity_source'])})")
        if e.get("unit_price"):
            lines.append(self._dec(f"{e['unit_price']:.3f} €{'/' + unit if unit else ''} ({self.tr(e.get('price_source') or '?')})"))
        if e.get("total"):
            lines.append(self.tr("Summe {0} €", self._dec(f"{e['total']:.2f}")))
        if e.get("note"):
            lines.append("💱 " + e["note"] if "EZB" in e["note"] or "EUR" in e["note"] else "📝 " + e["note"])
        return "\n".join(lines)

    async def handle_message(self, msg: dict[str, Any]) -> None:
        text = (msg.get("text") or msg.get("caption") or "").strip()
        file_id = None
        if msg.get("photo"):
            file_id = msg["photo"][-1]["file_id"]
        elif (msg.get("document") or {}).get("mime_type", "").startswith("image/"):
            file_id = msg["document"]["file_id"]
        if file_id and msg.get("media_group_id"):
            self._album_add(str(msg["media_group_id"]), file_id, text, msg.get("message_id") or 0)   # Album: alle Fotos sammeln, dann als ein Vorgang verarbeiten
            return
        if file_id:
            self.last_entry_id = None
            self._panel("processing", state="start")   # das Panel zeigt „Foto wird gelesen …“
            try:
                image = await get_bot(self.hass, self.o[CONF_TG_TOKEN]).download(file_id)
                if image:
                    await self.receive_photo(image, text)
                else:
                    await self._say(self.tr("Das Foto konnte ich nicht laden."))
            finally:
                self._panel("processing", state="done", entry=self.last_entry_id)
            return
        if text:
            await self.receive_text(text, sent_ts=msg.get("date"))

    ALBUM_WAIT = 3.0   # Sekunden Ruhe nach dem letzten Foto, bis das Album als vollständig gilt

    def _album_add(self, gid: str, file_id: str, caption: str, mid: int) -> None:
        albums = self.__dict__.setdefault("_albums", {})
        a = albums.setdefault(gid, {"items": [], "cancel": None})
        a["items"].append((mid, file_id, caption))
        if a["cancel"]:
            a["cancel"]()
        self._panel("processing", state="start")

        @callback
        def _go(_now) -> None:
            albums.pop(gid, None)
            self.hass.async_create_background_task(self._process_album(sorted(a["items"])), "drive_energy_doc_album")

        a["cancel"] = async_call_later(self.hass, self.ALBUM_WAIT, _go)

    async def _process_album(self, items: list[tuple[int, str, str]]) -> None:
        """Mehrere Fotos aus einer Telegram-Nachricht (z. B. Säule, Tacho, Beleg) sind ein Vorgang: der Reihe nach einlesen, dazwischen nicht nachfragen,
        am Ende die Plausibilität prüfen und eine gemeinsame Antwort schicken."""
        replies: list[str] = []
        try:
            async with self._upload_lock:
                self._batch = set()
                self._capture = []
                self.last_entry_id = None
                try:
                    bot = get_bot(self.hass, self.o[CONF_TG_TOKEN])
                    for _mid, file_id, caption in items:
                        image = await bot.download(file_id)
                        if image:
                            await self.receive_photo(image, caption)
                        else:
                            self._capture.append(self.tr("Das Foto konnte ich nicht laden."))
                    replies = list(self._capture)
                finally:
                    self._capture = None
                replies += self.batch_finish()
            if replies:
                await self._say("\n\n".join(dict.fromkeys(replies)))   # gleiche Meldungen nur einmal
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Album (%s) fehlgeschlagen", self.name)
        finally:
            self._panel("processing", state="done", entry=self.last_entry_id)

    async def _extra(self, item: str, rest: str, photo: str | None, values: dict | None = None) -> None:
        """Zubehör erfassen (AdBlue, Öl, Scheibenwischer …): Bezeichnung, optional Menge, Preis, Betrag, Foto.
        Ohne Zahlen wartet der Eintrag auf die nächste Nachricht mit Menge/Betrag."""
        values = values or receipt.parse_extra_values(rest)
        d = receipt.parse_date_hint(rest) or (values or {}).get("date")
        entry = self._new_manual_entry()
        self.last_extra_id = self.last_entry_id = entry["id"]
        entry["kind"] = "extra"
        entry["item"] = item
        entry["unit"] = {v[0].lower(): v[1] for v in messages.items().values()}.get(item.lower(), "")
        hm = (values or {}).get("time")
        if d:
            entry["ts"] = entry["ts_start"] = datetime.combine(d, dtime(*hm) if hm else dtime(12, 0), tzinfo=dt_util.DEFAULT_TIME_ZONE).timestamp()
        if values:
            self._apply_values(entry, values, photo)
        elif photo:
            entry["photos"].append(photo)
            entry["receipt"] = True
        self._stamp_km(entry)
        self.data["entries"].append(entry)
        self.data["entries"].sort(key=lambda x: x["ts"])
        self._save()
        self._notify_entities()
        if values:
            await self._say(self._summary(entry, self.tr("Zubehör erfasst: {0}", item or self.tr("Zubehör"))))
        else:
            self.data["awaiting_extra"] = {"id": entry["id"], "ts": time.time()}
            await self._say(self.tr("Zubehör „{0}“ angelegt. Tippe noch Menge und Betrag (z. B. 1 9,50) oder nur den Betrag.", item or self.tr("Zubehör")))

    @property
    def lang(self) -> str:
        return self.o.get(CONF_LANGUAGE) or self.hass.config.language or "en"

    def tr(self, key: str, *args) -> str:
        return messages.tr(self.lang, key, *args)

    def _dec(self, s: str) -> str:
        return s.replace(".", messages.decimal(self.lang))

    def _help(self) -> str:
        t = self.tr
        lines = [
            t("Drive Energy Doc: Hilfe ({0})", self.name),
            "",
            t("Beleg zum Tanken:"),
            t("• Foto vom Bon oder der Zapfsäule schicken"),
            t("• oder Text: Menge Betrag (45,93 105,13), mit Preis: Menge Preis Betrag, mit Datum davor: 27.10. 45,93 105,13"),
            t("• weiteres Foto zum letzten Tanken: Foto mit zusatz im Bildtext"),
            "",
            t("Zubehör (AdBlue, Öl, Scheibenwischer …):"),
            t("• Kennwort: +, e, x, extra, z, zub oder zubehör, dann Bezeichnung und Zahlen"),
            t("• Beispiele: + 24,90 · extra Öl 1 9,50 · x Scheibenwischer 24,90"),
            t("• auch als Bildtext zum Foto. Kurzwörter ohne Kennwort: adblue, öl, scheibenwasser, frostschutz"),
            "",
            t("Kilometerstand: Foto vom Tacho oder Text km 54210. Er wird dem Tankvorgang zugeordnet, der zur Sendezeit passt."),
            "",
            t("Rückfragen beantwortest du mit einem Datum (27.10.) oder mit neu."),
            t("Hilfe: ?, h, help oder hilfe"),
        ]
        return "\n".join(lines)

    async def receive_text(self, text: str, sent_ts: float | None = None) -> None:
        if text.strip().lower() in messages.keywords("help"):
            return await self._say(self._help())
        ow = self.data.get("awaiting_overwrite")
        if ow and time.time() - ow["ts"] < AWAIT_TTL:
            low = text.strip().lower()
            e = self.get_entry(ow["id"])
            if low in messages.keywords("yes") and e:
                self.data["awaiting_overwrite"] = None
                return await self._apply_and_report(e, ow["values"], ow.get("photo"))
            if low in messages.keywords("no"):
                self.data["awaiting_overwrite"] = None
                if ow.get("photo"):
                    await self._remove_files([ow["photo"]])
                self._save()
                return await self._say(self.tr("Gut, der neue Beleg wurde nicht übernommen."))
        up = self.data.get("unread_photo")
        if up and time.time() - up["ts"] < AWAIT_TTL and text.strip().lower() in (messages.keywords("doc") | messages.keywords("del")):
            self.data["unread_photo"] = None
            if text.strip().lower() in messages.keywords("del"):   # unlesbares Foto verwerfen
                await self._remove_files([up["name"]])
                self._save()
                return await self._say(self.tr("Foto gelöscht."))
            e = self._new_manual_entry()   # nur zur Dokumentation: Eintrag ohne Zahlen, zählt nicht in den Verbrauch
            e["kind"], e["item"], e["unit"] = "extra", self.tr("Dokumentation"), ""
            e["photos"].append(up["name"])
            e["receipt"] = True
            self.data["entries"].append(e)
            self.data["entries"].sort(key=lambda x: x["ts"])
            self._save()
            self._notify_entities()
            return await self._say(self.tr("Foto zur Dokumentation abgelegt."))
        px = receipt.parse_extra(text)
        if px:
            return await self._extra(px[0], px[1], None)
        km = receipt.parse_km(text)
        if km is not None:
            up = self.data.get("unread_photo")
            photo = up["name"] if up and time.time() - up["ts"] < AWAIT_TTL else None
            self.data["unread_photo"] = None
            return await self._odometer(km, photo, sent_ts)
        ao = self.data.get("awaiting_odo")
        if ao and time.time() - ao["ts"] < AWAIT_TTL:
            low = text.lower().strip()
            if ao.get("confirm") and ao.get("photo") and low in messages.keywords("new"):   # Tacho-Foto gehört zu keinem vorhandenen Eintrag: neuen anlegen
                self.data["awaiting_odo"] = None
                e = self._new_manual_entry()
                self.data["entries"].append(e)
                await self._apply_odometer(e, ao["km"], ao["photo"], 0)
                if not self.o.get(CONF_LEVEL):
                    await self._say(self.tr("Neuer Eintrag angelegt. Schick jetzt noch das Foto vom Beleg oder der Zapfsäule."))
                    self._remind_receipt(e)
                return
            if ao.get("confirm") and low in messages.keywords("yes"):
                self.data["awaiting_odo"] = None
                e = self.get_entry(ao["id"])
                if e:
                    return await self._apply_odometer(e, ao["km"], ao.get("photo"), time.time() - e["ts"])
            if low in messages.keywords("no"):
                self.data["awaiting_odo"] = None
                self._save()
                return await self._say(self.tr("Gut, den Kilometerstand habe ich nicht übernommen."))
            if not ao.get("confirm"):
                d = receipt.parse_date_hint(text)
                if d:
                    e = self._entry_on(d)
                    if e:
                        self.data["awaiting_odo"] = None
                        return await self._apply_odometer(e, ao["km"], ao.get("photo"), ao["sent"] - e["ts"])
                    return await self._say(self.tr("Zu {0} habe ich keinen Tankvorgang. Anderes Datum oder „nein“.", f"{d:%d.%m.%Y}"))
        aw = self.data.get("awaiting")
        if aw and time.time() - aw["ts"] < AWAIT_TTL:
            low = text.lower().strip()
            if low in messages.keywords("new"):
                entry = self._new_manual_entry()
                self.data["entries"].append(entry)
                self.data["awaiting"] = self.data["awaiting_overwrite"] = self.data["awaiting_odo"] = None
                await self._apply_and_report(entry, aw["values"], aw.get("photo"))
                return
            d = receipt.parse_date_hint(text)
            if d:
                entry = self._entry_on(d)
                if entry:
                    self.data["awaiting"] = self.data["awaiting_overwrite"] = self.data["awaiting_odo"] = None
                    await self._apply_and_report(entry, aw["values"], aw.get("photo"))
                else:
                    await self._say(self.tr("Zu {0} habe ich keinen Tankvorgang. Anderes Datum oder „neu“.", f"{d:%d.%m.%Y}"))
                return
        values = receipt.parse_text(text)
        aw_ad = self.data.get("awaiting_extra")
        if not values and not aw and aw_ad and time.time() - aw_ad["ts"] < AWAIT_TTL:
            values = receipt.parse_extra_values(text)  # bei Zubehör genügt auch nur der Betrag
        if values and not aw and aw_ad and time.time() - aw_ad["ts"] < AWAIT_TTL:
            e = self.get_entry(aw_ad["id"])
            if e:
                self._apply_values(e, values, None)
                self.data["awaiting_extra"] = None
                self._save()
                self._notify_entities()
                await self._say(self._summary(e, self.tr("Zubehör erfasst: {0}", e.get("item") or self.tr("Zubehör"))))
                return
        if not values:
            if aw:
                await self._say(self.tr("Antworte mit einem Datum (z. B. 27.10.) oder „neu“."))
            return
        up = self.data.get("unread_photo")   # unlesbares Foto: die getippten Werte gehören dazu
        photo = up["name"] if up and time.time() - up["ts"] < AWAIT_TTL else None
        self.data["unread_photo"] = None
        await self._route(values, photo)

    async def receive_photo(self, image: bytes, caption: str = "", sent_ts: float | None = None) -> None:
        for k in ("awaiting", "awaiting_overwrite", "awaiting_odo", "unread_photo"):   # ein neues Foto ersetzt alte, unbeantwortete Rückfragen (sonst kreisen sie)
            self.data[k] = None
        self._exif_pos = await self.hass.async_add_executor_job(receipt.exif_gps, image)   # vor dem Normalisieren: dabei gehen die Metadaten verloren
        image = await self.hass.async_add_executor_job(receipt.normalize, image)
        low = caption.lower().strip()
        px = receipt.parse_extra(caption)
        if px:
            item, rest = px
            values, box = receipt.parse_extra_values(rest), None
            if not values:
                ai = await receipt.ai_read(self.hass, self._ai_entity(), image, self.media_dir, self._pos, self._exif_pos)
                if ai and receipt.plausible(ai):
                    values, box = ai, ai.get("crop")
            name = await self.hass.async_add_executor_job(receipt.save_new_photo, image, box, self.photo_dir, values, sent_ts, item or "Zubehoer", self.orig_dir)
            return await self._extra(item, rest, name, values)
        extra = low.startswith(tuple(messages.keywords("photo")))
        values = None if extra else receipt.parse_text(caption)
        km = None if (extra or values) else receipt.parse_km(caption)   # Tacho-Foto mit Bildtext „km 54210“
        box = None
        ai = None
        rejected_km = None   # von der KI gelesen, aber unplausibel (Reihenfolge der Einträge): dem Nutzer sagen statt nur „nichts lesbar“
        if not extra and not values and km is None:
            t0 = time.time()
            ai = await receipt.ai_read(self.hass, self._ai_entity(), image, self.media_dir, self._pos, self._exif_pos)
            if not ai and time.time() - t0 < 60:   # schneller Fehlschlag (z. B. Überlastung des KI-Dienstes): einmal wiederholen
                await asyncio.sleep(3)
                ai = await receipt.ai_read(self.hass, self._ai_entity(), image, self.media_dir, self._pos, self._exif_pos)
            if ai and ai.get("busy"):   # KI überlastet: nichts ablegen, kein Eintrag
                return await self._say("⚠ " + self.tr("Die KI ist gerade überlastet. Bitte schick das Foto in ein paar Minuten noch einmal.") + " " + self.tr("Es wurde nichts gespeichert."))
            if ai and ai.get("error"):   # KI hat die Anfrage abgelehnt (z. B. Einstellungen/Konto der KI): nichts ablegen, deutlich sagen statt „nichts lesbar“
                return await self._say("⚠ " + self.tr("Die gewählte KI hat die Anfrage abgelehnt ({0}). Details stehen im Home-Assistant-Protokoll.", ai["error"]) + " " + self.tr("Es wurde nichts gespeichert."))
            if ai and receipt.plausible(ai):
                values, box = ai, ai.get("crop")
            elif ai and ai.get("odometer") and self._km_sane(ai["odometer"], ts=sent_ts):   # mit bekannter Aufnahme-/Sendezeit gegen die Reihenfolge der Einträge prüfen
                km, box = float(ai["odometer"]), ai.get("crop")           # nur Kilometerstand erkannt: Foto vom Tacho
            elif ai and ai.get("odometer"):
                rejected_km = float(ai["odometer"])
                _LOGGER.warning("Kilometerstand %s vom Foto passt nicht zur Reihenfolge der Einträge (%s)", rejected_km, self.name)
        info = values if isinstance(values, dict) and values else (ai if isinstance(ai, dict) and not ai.get("busy") and not ai.get("error") else None)
        name = await self.hass.async_add_executor_job(receipt.save_new_photo, image, box, self.photo_dir, info, sent_ts, "Tacho" if (km is not None and not values) else ("Zusatzfoto" if extra else None), self.orig_dir)
        cat = (values or {}).get("category") if isinstance(values, dict) else None
        if cat in ("adblue", "oil", "washer", "carwash", "other"):   # Beleg für Zubehör/Verbrauchsmaterial: eigener Eintrag, nie einen Tankvorgang überschreiben
            item = {"adblue": "AdBlue", "oil": "Öl", "washer": "Scheibenreiniger", "carwash": "Waschen"}.get(cat) or (values.get("item") or "Zubehör")
            item = self.tr(item) if cat != "other" else item
            return await self._extra(item, "", name, {k: v for k, v in values.items() if k != "odometer"})
        if km is not None:
            return await self._odometer(km, name, sent_ts)
        if extra or not values:
            d = receipt.parse_date_hint(caption)
            target = self._entry_on(d, True) if d else (self._newest_within(48 * 3600) or (self.data["entries"][-1] if self.data["entries"] else None))
            pend = self.detector.pending or (self.detector_el.pending if self.detector_el else None)
            if target is None and pend:
                pend.extras.setdefault("extra_photos", []).append(name)
                self._save()
                await self._say(self.tr("Zusatzfoto vorgemerkt, es wird dem Tankvorgang beim Abschluss zugefügt."))
            elif target and (extra or d):   # ausdrücklich Zusatzfoto bzw. Datum im Bildtext; sonst nachfragen statt irgendwo anhängen
                target["photos"].append(name)
                self._save()
                self._notify_entities()
                await self._say(self.tr("Zusatzfoto gespeichert.") if extra else self.tr("Werte nicht lesbar, das Foto habe ich als Zusatzfoto abgelegt. Tippe sie sonst: Menge Betrag, z. B. 45,93 105,13"))
            else:   # nichts lesbar und noch kein Eintrag: Foto merken, der Kilometerstand kommt als Text
                self.data["unread_photo"] = {"name": name, "ts": time.time()}
                self._save()
                if rejected_km is not None:
                    await self._say(self.tr("Auf dem Foto steht der Kilometerstand {0} km, das passt aber nicht zur Reihenfolge der Einträge. Schick den Stand als Text (z. B. „km {0}“), wenn er stimmt, oder lege das Foto nur zur Dokumentation ab, oder lösche es.", self._fmt_km(rejected_km)))
                else:
                    await self._say(self.tr("Auf dem Foto konnte ich weder Beleg noch Kilometerstand lesen. Schick den Kilometerstand als Text (z. B. „km 61240“) oder lege das Foto nur zur Dokumentation ab, oder lösche es."))
            return
        await self._route(values, name)

    # ---------------------------------------------------------------- Kilometerstand (Tacho-Foto oder Text)
    @staticmethod
    def _fmt_km(km: float) -> str:
        return f"{km:,.0f}".replace(",", ".")

    async def _odometer(self, km: float, photo: str | None, sent_ts: float | None = None) -> None:
        """Kilometerstand dem Tankvorgang zuordnen, der zur Sendezeit passt (Foto oder Text)."""
        sent = sent_ts or time.time()
        pend = self._valid_pending()
        if pend and pend.valid:  # es wird gerade getankt oder geladen: beim Abschluss übernehmen
            pend.extras["odometer"] = {"km": km, "photo": photo}
            self._save()
            await self._say(self.tr("Kilometerstand {0} km vorgemerkt, er wird beim Abschluss des laufenden Tankvorgangs übernommen.", self._fmt_km(km)))
            return
        recent = max(self.data["entries"], key=lambda x: x.get("created", 0), default=None)
        if recent and recent.get("kind") == "extra" and recent.get("odometer_source") in (None, "bekannt") and time.time() - recent.get("created", 0) <= OPEN_WINDOW:
            # der zuletzt angelegte Eintrag ist Zubehör ohne echten Kilometerstand: der Tacho gehört dazu (statt nur der zuletzt bekannte Stand)
            return await self._apply_odometer(recent, km, photo, 0)
        photo_only = not self.o.get(CONF_LEVEL)
        open_e = self._open_entry("odometer") if photo_only else None
        if open_e:
            sent = open_e["ts"]   # Beleg kam zuerst: der Kilometerstand gehört zu diesem Eintrag
        m = stats.match_odometer(self.data["entries"], km, sent)
        from_photo = photo is not None   # von der KI aus einem Foto gelesen (nicht getippt): im Zweifel weglassen statt nachfragen
        if photo_only and m["status"] == "ok" and not m.get("backwards") and not open_e:
            # Der zeitlich nächste Eintrag hat schon einen eigenen Kilometerstand und der neue liegt deutlich darüber (mehr als 50 km):
            # das ist der Tacho zu einem neuen Tank- oder Ladevorgang, nicht ein weiteres Foto zum vorigen Eintrag
            od = m["entry"].get("odometer")
            if od is not None and km - float(od) > 50:
                m = {"status": "none"}
        if photo_only and m["status"] in ("none", "too_old"):
            # reiner Foto-Betrieb: der Tacho kommt zuerst, der Beleg wird danach (bis 48 h) diesem Eintrag zugeordnet
            e = self._new_manual_entry()
            self._retime(e, sent)
            self.data["entries"].append(e)
            self.data["entries"].sort(key=lambda x: x["ts"])
            await self._apply_odometer(e, km, photo, 0)
            await self._say(self.tr("Neuer Eintrag angelegt. Schick jetzt noch das Foto vom Beleg oder der Zapfsäule."))
            self._remind_receipt(e)
            return
        if m["status"] == "none":
            await self._say(self.tr("Es gibt noch keinen Tankvorgang, dem ich den Kilometerstand zuordnen könnte."))
            return
        e = m["entry"]
        when = dt_util.as_local(dt_util.utc_from_timestamp(e["ts"])).strftime("%d.%m.%Y %H:%M")
        if m["status"] == "too_old":
            self.data["awaiting_odo"] = {"km": km, "photo": photo, "ts": time.time(), "sent": sent}
            self._save()
            await self._say(self.tr("Zu dieser Uhrzeit gibt es keinen Tankvorgang (nächster: {0}). Antworte mit dem Datum (z. B. 27.10.), dann ordne ich {1} km diesem Tankvorgang zu, oder mit „nein“.", when, self._fmt_km(km)))
            return
        if (m["status"] == "mismatch" or m.get("backwards")) and from_photo:
            return await self._skip_km(e, km, photo, "Kilometerstand passt nicht zum Eintrag")
        if m["status"] == "mismatch" or m.get("backwards"):
            self.data["awaiting_odo"] = {"id": e["id"], "km": km, "photo": photo, "ts": time.time(), "confirm": True}
            self._save()
            why = self.tr("liegt unter dem Stand beim vorigen Tanken ({0} km)", self._fmt_km(m["prev_odo"])) if m.get("backwards") else self.tr("weicht stark vom gespeicherten Stand ({0} km) ab", self._fmt_km(e["odometer"]))
            await self._say(self.tr("Der Kilometerstand {0} km {1}. Tankvorgang: {2}. Antworte „ja“, um ihn trotzdem zu übernehmen, oder „nein“.", self._fmt_km(km), why, when))
            return
        chk = self._check_cons(self.data["entries"], e, km)
        if chk and not chk["ok"] and from_photo:
            return await self._skip_km(e, km, photo, "Verbrauch unplausibel")
        if chk and not chk["ok"]:   # getippter Stand, Verbrauch passt nicht zu Tankmenge und Durchschnitt: nachfragen
            self.data["awaiting_odo"] = {"id": e["id"], "km": km, "photo": photo, "ts": time.time(), "confirm": True}
            self._save()
            why = self.tr("würde bei {0} km seit dem letzten Tanken {1} ergeben (Durchschnitt {2})", self._fmt_km(chk["driven"]), self._cons_txt(chk["cons"], chk.get("energy")), self._cons_txt(chk["avg"], chk.get("energy")))
            await self._say(self.tr("Der Kilometerstand {0} km {1}. Tankvorgang: {2}. Antworte „ja“, um ihn trotzdem zu übernehmen, oder „nein“.", self._fmt_km(km), why, when))
            return
        await self._apply_odometer(e, km, photo, m["dt"])

    async def _skip_km(self, entry: dict, km: float, photo: str | None, why: str) -> None:
        """Zweifel am Kilometerstand vom Foto: weglassen (keine Rückfrage), das Foto bleibt als Zusatzfoto am Eintrag."""
        _LOGGER.info("Kilometerstand %s vom Foto ausgelassen (%s, %s)", km, why, self.name)
        if photo:
            entry["photos"].append(photo)
        self._save()
        self._notify_entities()
        await self._say(self.tr("Zusatzfoto gespeichert."))

    def unit_of(self, e: dict | None) -> str:
        """Einheit der Menge eines Eintrags: kWh bei Strom (auch im Plug-in-Hybrid), sonst die des Fahrzeugs."""
        return "kWh" if e and e.get("energy") == "electric" else self.unit

    def _cons_txt(self, value: float, energy: str | None = None) -> str:
        return self._dec(f"{value:.1f}") + f" {'kWh' if energy == 'electric' else self.unit}/100 km"

    async def _apply_odometer(self, entry: dict, km: float, photo: str | None, dt: float) -> None:
        if self._batch is not None:
            self._batch.add(entry["id"])
        source = "foto" if photo else "manuell"
        if not stats.km_better(entry, source):   # der Eintrag hat schon einen besseren Stand (Sensor des Autos): nur das Foto ablegen
            if photo:
                entry["photos"].append(photo)
            self._save()
            self._notify_entities()
            return await self._say(self.tr("Zusatzfoto gespeichert."))
        entry["odometer"] = float(km)
        entry["odometer_source"] = source
        if photo:
            entry["photos"].append(photo)
        self._save()
        self._notify_entities()
        when = dt_util.as_local(dt_util.utc_from_timestamp(entry["ts"])).strftime("%d.%m.%Y %H:%M")
        late = " " + self.tr("(Nachricht {0} h nach dem Tanken)" if dt > 0 else "(Nachricht {0} h vor dem Tanken)", self._dec(f"{abs(dt) / 3600:.1f}")) if abs(dt) > 3 * 3600 else ""
        await self._say(self.tr("Kilometerstand {0} km für den Tankvorgang vom {1} übernommen{2}.", self._fmt_km(km), when, late))

    # ---------------------------------------------------------------- Zuordnung
    def _energy_of(self, values: dict | None) -> str | None:
        """Plug-in-Hybrid: ``electric`` bei einem Ladebeleg, sonst ``fuel``. Andere Fahrzeuge: None (keine Unterscheidung)."""
        if not self.phev:
            return None
        return "electric" if (values or {}).get("category") == "charging" else "fuel"

    @staticmethod
    def _fits_energy(e: dict, energy: str | None) -> bool:
        """Gehört der Eintrag zur gesuchten Energieart? Noch leere Einträge (Tacho-Foto, nichts gelesen) passen zu beiden."""
        return energy is None or stats.energy_of(e) == energy or (e.get("quantity") is None and not e.get("receipt"))

    def _entry_on(self, d, any_kind: bool = False, energy: str | None = None) -> dict | None:
        hits = [e for e in self.data["entries"] if dt_util.as_local(dt_util.utc_from_timestamp(e["ts"])).date() == d and (any_kind or e.get("kind") != "extra") and (e.get("kind") == "extra" or self._fits_energy(e, energy))]
        return hits[-1] if hits else None

    def _newest_within(self, seconds: float, energy: str | None = None) -> dict | None:
        for e in reversed(self.data["entries"]):
            if time.time() - e["ts"] <= seconds and not e.get("receipt") and e.get("kind") != "extra" and self._fits_energy(e, energy):
                return e
        return None

    def _new_manual_entry(self) -> dict:
        return {
            "id": uuid.uuid4().hex[:12], "created": time.time(), "ts": time.time(), "ts_start": time.time(), "odometer": self._read_float(self.o.get(CONF_ODOMETER)), "odometer_source": "sensor" if self._read_float(self.o.get(CONF_ODOMETER)) is not None else None,
            "lat": self._pos[0] if self._pos else None, "lon": self._pos[1] if self._pos else None, "station": None, "address": None,
            "station_id": None, "level_from": None, "level_to": None, "quantity": None, "quantity_source": "manuell", "unit_price": None,
            "price_source": None, "total": None, "photos": [], "receipt": False, "note": "",
        }

    def _check_cons(self, entries: list[dict], entry: dict, km: float):
        """Verbrauchsprüfung eines Kilometerstands. Beim Plug-in-Hybrid entfällt sie: Benzin und Strom werden im Wechsel verbraucht, der Verbrauch je Energieart ist dafür zu unterschiedlich."""
        return None if self.phev else stats.check_consumption(entries, entry, km)

    def _last_known_km(self, ts: float) -> float | None:
        """Zuletzt bekannter Kilometerstand bis zum Zeitpunkt ``ts`` (Tacho-Foto, Beleg, Sensor oder von Hand), geschätzte Stände zählen nicht."""
        km = [e for e in self.data["entries"] if e.get("odometer") is not None and e.get("odometer_source") != "bekannt" and e["ts"] <= ts + 60]
        return float(max(km, key=lambda x: x["ts"])["odometer"]) if km else None

    def _stamp_km(self, entry: dict) -> None:
        """Zubehör ohne eigenen Kilometerstand bekommt den zuletzt bekannten (wie beim Tanken); ein Tacho-Foto oder ein getippter Stand ersetzt ihn später."""
        if entry.get("odometer") is None:
            km = self._last_known_km(entry["ts"])
            if km is not None:
                entry["odometer"], entry["odometer_source"] = km, "bekannt"

    def _km_sane(self, km, exclude: str | None = None, ts: float | None = None) -> bool:
        """Von der KI gelesener Kilometerstand möglich? Siehe stats.km_plausible (mit Datum vom Beleg: Reihenfolge der Einträge, sonst Abstand zum Mittelwert)."""
        return stats.km_plausible(self.data["entries"], km, ts, exclude)

    @staticmethod
    def _retime(entry: dict, ts: float) -> None:
        """Zeitpunkt eines Eintrags setzen. Ein beim Anlegen vom Sensor gelesener Kilometerstand passt nur zu \"jetzt\": liegt der Zeitpunkt (z. B. Datum vom Beleg) mehr als 3 Stunden davon entfernt, wird er verworfen."""
        entry["ts"] = entry["ts_start"] = ts
        if entry.get("odometer_source") == "sensor" and abs(ts - entry.get("created", ts)) > 3 * 3600:
            entry["odometer"] = None
            entry["odometer_source"] = None

    def _entry_by_km(self, km: float, tolerance: float = 50.0) -> dict | None:
        """Eintrag ohne Beleg, dessen Kilometerstand (vom Tacho-Foto) fast genau zum Stand auf dem Beleg passt: so finden Beleg und Tacho auch bei gemischter Reihenfolge zusammen."""
        c = [e for e in self.data["entries"] if e.get("kind") != "extra" and not e.get("receipt") and e.get("quantity") is None and e.get("odometer") is not None and abs(e["odometer"] - km) <= tolerance]
        return min(c, key=lambda e: abs(e["odometer"] - km)) if c else None

    def _open_entry(self, need: str, energy: str | None = None) -> dict | None:
        """Zuletzt angelegter Eintrag (der letzten Stunden), dem noch der Beleg ("receipt") bzw. der Kilometerstand ("odometer") fehlt.
        Damit gehören Tacho-Foto und Beleg zusammen, egal in welcher Reihenfolge sie kommen und welches Datum auf dem Beleg steht."""
        es = [e for e in self.data["entries"] if e.get("kind") != "extra" and e.get("created") and self._fits_energy(e, energy)]
        if not es:
            return None
        e = max(es, key=lambda x: x["created"])
        if time.time() - e["created"] > OPEN_WINDOW:
            return None
        if need == "receipt" and not e.get("receipt") and e.get("quantity") is None:
            return e
        if need == "odometer" and e.get("odometer") is None:
            return e
        return None

    def _remind_receipt(self, entry: dict, delay: float = REMIND_AFTER) -> None:
        """Nach einer Weile einmal nachfragen, wenn zum neuen Eintrag (z. B. vom Tacho-Foto) noch kein Beleg gekommen ist."""
        eid = entry["id"]

        async def _cb(_now) -> None:
            e = self.get_entry(eid)
            if not e or e.get("receipt") or e.get("quantity"):
                return
            when = dt_util.as_local(dt_util.utc_from_timestamp(e["ts"])).strftime("%d.%m. %H:%M")
            await self._say(self.tr("Zum Eintrag vom {0} ({1} km) fehlt noch der Beleg oder das Foto der Zapfsäule. Bitte schick es noch.", when, self._fmt_km(e.get("odometer") or 0)), quick=True)

        self._unsubs.append(async_call_later(self.hass, delay, _cb))

    def _same_event(self, values: dict, energy: str | None) -> tuple[dict, str] | None:
        """Gehören Säulen-Display und Beleg zum selben Vorgang? Ein gerade erst angelegter Eintrag (letzte 6 Stunden) mit gleichem Preis je Einheit, der eine ohne Station (aus dem Display),
        der andere mit Station (vom Beleg). Menge und Betrag dürfen abweichen: auf einem unscharfen Display werden Ziffern oft falsch gelesen. Rückgabe: (Eintrag, "receipt" | "display"),
        „receipt“ = der neue Beleg gehört zum Display-Eintrag und gilt als genauer, „display“ = das neue Display-Foto gehört zum Beleg-Eintrag."""
        p = values.get("unit_price")
        if not p:
            return None
        has_station = bool(values.get("station"))
        for e in reversed(self.data["entries"]):
            if e.get("kind") == "extra" or not e.get("receipt") or not self._fits_energy(e, energy):
                continue
            if time.time() - e.get("created", 0) > OPEN_WINDOW or not e.get("unit_price") or abs(e["unit_price"] - p) > 0.0005:
                continue
            if has_station and not e.get("station"):
                return e, "receipt"
            if not has_station and e.get("station"):
                return e, "display"
        return None

    def _duplicate_of(self, values: dict, energy: str | None) -> dict | None:
        """Ist dieser Beleg (gleiche Menge und gleicher Betrag) schon als Eintrag vorhanden? Mit Datum vom Beleg: am selben Tag, ohne Datum (Säulen-Display): in den letzten 3 Tagen.
        Zubehör zählt nicht (gleiche Preise kommen dort öfter vor, z. B. Autowäsche)."""
        q, tot = values.get("quantity"), values.get("total")
        if not (q and tot):
            return None
        d = values.get("date")
        for e in reversed(self.data["entries"]):
            if e.get("kind") == "extra" or not e.get("receipt") or not self._fits_energy(e, energy):
                continue
            if abs((e.get("quantity") or 0) - q) >= 0.011 or abs((e.get("total") or 0) - tot) >= 0.011:
                continue
            recent = time.time() - e.get("created", 0) <= OPEN_WINDOW   # gerade erst angelegt (z. B. aus Säulen-Foto und Tacho): dessen Datum ist nur der Zeitpunkt des Uploads
            if d is not None:
                if recent or dt_util.as_local(dt_util.utc_from_timestamp(e["ts"])).date() == d:
                    return e
            elif time.time() - max(e.get("ts", 0), e.get("created", 0)) <= 3 * 86400:
                return e
        return None

    async def _ask_duplicate(self, target: dict, values: dict, photo: str | None) -> None:
        """Gleicher Beleg noch einmal geschickt: ja = dem vorhandenen Eintrag zuordnen (Foto kommt dazu), nein = verwerfen. Es entsteht kein zweiter Eintrag."""
        when = dt_util.as_local(dt_util.utc_from_timestamp(target["ts"])).strftime("%d.%m.%Y %H:%M")
        have = ", ".join(x for x in (self._dec(f"{target['quantity']:.2f}") + f" {self.unit_of(target)}" if target.get("quantity") else "", self._dec(f"{target['total']:.2f}") + " €" if target.get("total") else "") if x)
        self.data["awaiting_overwrite"] = {"id": target["id"], "values": {k: (v if k != "date" else None) for k, v in values.items()}, "photo": photo, "ts": time.time()}
        self._save()
        await self._say(self.tr("Dieser Beleg ist schon eingetragen (Eintrag vom {0}: {1}). Antworte „ja“, um ihn trotzdem zu überschreiben, oder „nein“.", when, have))

    async def _route(self, values: dict, photo: str | None) -> None:
        d = values.get("date")
        if values.get("odometer"):   # Kilometerstand vom Beleg gegen die Reihenfolge der Einträge prüfen (Datum/Uhrzeit vom Beleg), unmöglicher Stand: ignorieren
            hm = values.get("time")
            when = (dt_util.start_of_local_day(d).timestamp() + ((hm[0] * 3600 + hm[1] * 60) if hm else 12 * 3600)) if d else time.time()
            if not self._km_sane(values["odometer"], ts=when):
                _LOGGER.info("Kilometerstand %s vom Beleg unplausibel, ignoriert (%s)", values["odometer"], self.name)
                values = {**values, "odometer": None}
        en = self._energy_of(values)   # Plug-in-Hybrid: Tanken und Laden sind getrennte Einträge
        se = self._same_event(values, en)
        if se is not None:   # Display und Beleg desselben Vorgangs: ein Eintrag, die Werte vom Beleg gelten
            ev, mode = se
            if mode == "receipt":
                if d:
                    hm = values.get("time")
                    self._retime(ev, dt_util.start_of_local_day(d).timestamp() + ((hm[0] * 3600 + hm[1] * 60) if hm else 12 * 3600))
                    self.data["entries"].sort(key=lambda x: x["ts"])
                await self._apply_and_report(ev, values, photo)
            else:
                if photo:
                    ev["photos"].append(photo)
                self.last_entry_id = ev["id"]
                self._save()
                self._notify_entities()
                await self._say(self.tr("Zusatzfoto gespeichert."))
            return
        dup = self._duplicate_of(values, en)
        if dup is not None:   # derselbe Beleg ist schon eingetragen: nicht noch einmal anlegen
            if time.time() - dup.get("created", 0) <= OPEN_WINDOW:
                # gerade erst angelegt (Säule und Tacho zuerst, dann der Beleg): der Beleg gehört zu diesem Eintrag, Datum, Uhrzeit, Station und Preis vom Beleg gelten
                if d:
                    hm = values.get("time")
                    self._retime(dup, dt_util.start_of_local_day(d).timestamp() + ((hm[0] * 3600 + hm[1] * 60) if hm else 12 * 3600))
                    self.data["entries"].sort(key=lambda x: x["ts"])
                await self._apply_and_report(dup, values, photo)
            else:
                await self._ask_duplicate(dup, values, photo)   # älterer Eintrag: nachfragen
            return
        photo_only = not (self.detector_el if en == "electric" else self.o.get(CONF_LEVEL))  # ohne Füllstandssensor (Tank bzw. Akku): jeder Beleg ohne passenden Eintrag legt einen neuen an
        open_e = ((self._entry_by_km(values["odometer"]) if values.get("odometer") else None) or self._open_entry("receipt", en)) if photo_only else None
        if open_e:   # das Tacho-Foto kam zuerst und hat schon eine neue Zeile angelegt: der Beleg gehört dazu (Datum und Uhrzeit vom Beleg gelten)
            if d:
                hm = values.get("time")
                self._retime(open_e, dt_util.start_of_local_day(d).timestamp() + ((hm[0] * 3600 + hm[1] * 60) if hm else 12 * 3600))
                self.data["entries"].sort(key=lambda x: x["ts"])
            await self._apply_and_report(open_e, values, photo)
            return
        pv = self._pending_for(en)
        if pv is not None and pv.valid and (not d or d == dt_util.now().date()):   # es wird gerade getankt/geladen (oder gerade fertig): auch ein Beleg von heute gehört zu diesem Vorgang
            pv.extras["receipt"] = {"values": {k: v for k, v in values.items() if k != "date"}, "photo": photo}
            self._save()
            await self._say(self.tr("Beleg vorgemerkt, er wird beim Abschluss des laufenden Tankvorgangs übernommen."))
            return
        if d:
            target = self._entry_on(d, False, en)
            if not target and photo_only:
                target = self._new_manual_entry()
                hm = values.get("time")
                self._retime(target, dt_util.start_of_local_day(d).timestamp() + ((hm[0] * 3600 + hm[1] * 60) if hm else 12 * 3600))
                self.data["entries"].append(target)
                self.data["entries"].sort(key=lambda x: x["ts"])
            if not target:
                self.data["awaiting"] = {"values": {**values, "date": None}, "photo": photo, "ts": time.time()}
                await self._say(self.tr("Zu {0} gibt es keinen Tankvorgang. Antworte mit einem anderen Datum oder „neu“.", f"{d:%d.%m.%Y}"))
                return
        elif (self._pending_for(en) or None) and self._pending_for(en).valid:
            self._pending_for(en).extras["receipt"] = {"values": {k: v for k, v in values.items() if k != "date"}, "photo": photo}
            self._save()
            await self._say(self.tr("Beleg vorgemerkt, er wird beim Abschluss des laufenden Tankvorgangs übernommen."))
            return
        else:
            target = self._newest_within(48 * 3600, en)
        if target is None and photo_only:
            target = self._new_manual_entry()
            self.data["entries"].append(target)
        if target is None:
            self.data["awaiting"] = {"values": {**values, "date": None}, "photo": photo, "ts": time.time()}
            recent = ", ".join(dt_util.as_local(dt_util.utc_from_timestamp(e["ts"])).strftime("%d.%m.") for e in self.data["entries"][-3:])
            await self._say(self.tr("Dazu habe ich keinen offenen Tankvorgang.") + (" " + self.tr("Letzte: {0}.", recent) if recent else "") + " " + self.tr("Antworte mit dem Datum (z. B. 27.10.) oder „neu“ für einen neuen Eintrag."))
            return
        if target.get("receipt") and (values.get("quantity") or values.get("total")):
            same = abs((target.get("quantity") or 0) - (values.get("quantity") or 0)) < 0.011 and abs((target.get("total") or 0) - (values.get("total") or 0)) < 0.011
            when = dt_util.as_local(dt_util.utc_from_timestamp(target["ts"])).strftime("%d.%m.%Y %H:%M")
            have = ", ".join(x for x in (self._dec(f"{target['quantity']:.2f}") + f" {self.unit_of(target)}" if target.get("quantity") else "", self._dec(f"{target['total']:.2f}") + " €" if target.get("total") else "") if x)
            self.data["awaiting_overwrite"] = {"id": target["id"], "values": {k: (v if k != "date" else None) for k, v in values.items()}, "photo": photo, "ts": time.time()}
            self._save()
            key = "Dieser Beleg ist schon eingetragen (Eintrag vom {0}: {1}). Antworte „ja“, um ihn trotzdem zu überschreiben, oder „nein“." if same else "Es gibt schon einen Beleg-Eintrag vom {0} ({1}). Antworte „ja“, um ihn mit dem neuen Beleg zu überschreiben, oder „nein“."
            await self._say(self.tr(key, when, have))
            return
        await self._apply_and_report(target, values, photo)

    async def _apply_and_report(self, entry: dict, values: dict, photo: str | None) -> None:
        self.last_entry_id = entry["id"]
        rkm = values.get("odometer")
        batch = self._batch is not None
        if batch:
            self._batch.add(entry["id"])
        if rkm:   # Kilometerstand vom Beleg ist die schlechteste Quelle (von Hand getippt): nur wenn der Eintrag noch keinen hat und der Verbrauch passt, sonst weglassen
            self._apply_values(entry, {**values, "odometer": None}, photo)
            if not stats.km_better(entry, "beleg"):
                _LOGGER.info("Kilometerstand %s vom Beleg ignoriert: der Eintrag hat schon einen besseren (%s)", rkm, self.name)
            else:
                chk = self._check_cons(self.data["entries"], entry, float(rkm))
                if chk and not chk["ok"]:
                    _LOGGER.info("Kilometerstand %s vom Beleg ausgelassen (Verbrauch unplausibel, %s)", rkm, self.name)
                else:
                    entry["odometer"], entry["odometer_source"] = float(rkm), "beleg"
        else:
            self._apply_values(entry, values, photo)
        self._save()
        self._notify_entities()
        warn = "" if receipt.plausible(entry) else "\n" + self.tr("⚠️ Menge × Preis passt nicht zum Betrag, bitte prüfen.")
        chk = self._check_cons(self.data["entries"], entry, entry["odometer"]) if entry.get("odometer") is not None and not batch else None
        if chk and not chk["ok"]:
            warn += "\n" + self.tr("⚠️ Verbrauch ungewöhnlich: {0} bei {1} km seit dem letzten Tanken (Durchschnitt {2}), bitte Kilometerstand prüfen.", self._cons_txt(chk["cons"], chk.get("energy")), self._fmt_km(chk["driven"]), self._cons_txt(chk["avg"], chk.get("energy")))
        await self._say(self._summary(entry, self.tr("Beleg übernommen")) + warn)

    def _apply_values(self, entry: dict, values: dict, photo: str | None) -> None:
        q, p, t = values.get("quantity"), values.get("unit_price"), values.get("total")
        if q:
            entry["quantity"], entry["quantity_source"] = round(q, 2), "beleg"
        if p:
            entry["unit_price"], entry["price_source"] = round(p, 3), "beleg"
        if t:
            entry["total"] = round(t, 2)
        elif entry.get("quantity") and entry.get("unit_price"):
            entry["total"] = round(entry["quantity"] * entry["unit_price"], 2)
        if t and q and not p:
            entry["unit_price"], entry["price_source"] = round(t / q, 3), "beleg"
        if values.get("station"):
            entry["station"] = values["station"]  # Name und Anschrift vom Beleg gehen vor (genauer als die Suche nach der nächsten Tankstelle)
            if values.get("address"):
                entry["address"] = values["address"]
        if values.get("odometer") and stats.km_better(entry, "beleg"):
            entry["odometer"], entry["odometer_source"] = float(values["odometer"]), "beleg"   # nur wenn kein besserer Stand da ist
        if q or p or t:
            entry["receipt"] = True
        ct = charge.parse_type(values.get("charge_type"))
        if ct and entry.get("kind") != "extra" and entry.get("charge_src") != "sensor" and (self.electric or entry.get("energy") == "electric" or values.get("category") == "charging"):
            entry["charge_type"], entry["charge_src"] = ct, "beleg"   # Ladeart vom Beleg oder der Säule, nur der Sensor des Autos geht vor
        if values.get("fuel_grade") in receipt.FUEL_GRADES and entry.get("kind") != "extra" and entry.get("energy") != "electric" and values.get("category") in (None, "fuel"):
            entry["fuel"] = values["fuel_grade"]   # Sorte vom Beleg (z. B. Super E10 oder Super Plus)
        if self.phev and values.get("category") in ("fuel", "charging") and entry.get("kind") != "extra":
            if values["category"] == "charging":
                entry["energy"] = "electric"
            else:
                entry.pop("energy", None)
        note = self.currency_note(values.get("orig"))
        if values.get("orig") and note:
            entry["orig"] = {**values["orig"], "note": note}   # Originalwerte und Umrechnung: die Währung lässt sich später von Hand ändern
        if note and note not in (entry.get("note") or ""):   # jede Umrechnung steht in der Notiz, aber nie doppelt (derselbe Beleg zweimal angewendet)
            entry["note"] = f"{entry['note']} · {note}" if entry.get("note") else note
        if photo:
            entry["photos"].insert(0, photo)

    def currency_note(self, orig: dict | None) -> str:
        """Notiz für einen Beleg in Fremdwährung: Originalpreis und -währung, dazu der verwendete Kurs."""
        if not orig:
            return ""
        dec = messages.decimal(self.lang)
        f = lambda x, n: f"{x:.{n}f}".replace(".", dec)   # noqa: E731
        parts = []
        if orig.get("total"):
            parts.append(f"{f(orig['total'], 2)} {orig['currency']}")
        if orig.get("unit_price"):
            parts.append(self.tr("Preis {0}", f"{f(orig['unit_price'], 3)} {orig['currency']}"))
        original = ", ".join(parts)
        if orig.get("unknown"):
            return "⚠ " + self.tr("Keine Währung erkannt, Land nicht ermittelbar: Werte als Euro angenommen. Bitte Währung prüfen.")
        hint = (self.tr("Währung manuell gesetzt: {0}.", orig["currency"]) + " ") if orig.get("manual") else ""
        if orig.get("assumed"):
            hint = self.tr("Keine Währung erkannt, Landeswährung {0} angenommen ({1}).", orig["currency"], orig["assumed"]) + " "   # Währung aus dem Land der GPS-Position
        if orig.get("currency") == "EUR":
            return hint.strip()
        if not orig.get("rate"):
            return hint + self.tr("Beleg in {0}, Umrechnung nicht möglich, Werte nicht in Euro! Original: {1}", orig["currency"], original)
        day = dt_util.parse_date(orig["date"]) if orig.get("date") else None
        eur = f"{receipt.round_half_up(orig['total'] / orig['rate'], 2):.2f}".replace(".", dec) if orig.get("total") else "?"
        return hint + self.tr("Original: {0} → {4} € · Kurs: 1 EUR = {1} {2} (EZB, {3})", original, f(orig["rate"], 4), orig["currency"], day.strftime("%d.%m.%Y") if day else orig.get("date") or "", eur)

    async def set_currency(self, entry_id: str, currency: str) -> bool:
        """Währung eines Belegs von Hand ändern (z. B. wenn sie nicht erkannt wurde): Betrag und Preis werden aus den Originalwerten zum Tageskurs neu umgerechnet, die Notiz wird ersetzt."""
        e = self.get_entry(entry_id)
        cur = str(currency or "").strip().upper()
        o = (e or {}).get("orig")
        if not e or not o or not re.fullmatch(r"[A-Z]{3}", cur):
            return False
        total, price = o.get("total"), o.get("unit_price")
        rate, day = None, None
        if cur != "EUR":
            on = dt_util.as_local(dt_util.utc_from_timestamp(e["ts"])).date()
            got = await receipt.eur_rate(self.hass, cur, on)
            if got:
                rate, day = got
        new = {"currency": cur, "total": total, "unit_price": price, "rate": rate, "date": day, "assumed": None, "manual": True}
        div = rate or 1.0
        if total:
            e["total"] = receipt.round_half_up(total / div, 2)
        if price:
            e["unit_price"], e["price_source"] = receipt.round_half_up(price / div, 3), "beleg"
        if not total and e.get("quantity") and e.get("unit_price"):
            e["total"] = round(e["quantity"] * e["unit_price"], 2)
        note = self.currency_note(new)
        keep = (e.get("note") or "").replace(o.get("note") or "", "").strip(" ·")
        e["note"] = f"{keep} · {note}" if keep and note else (keep or note)
        e["orig"] = {**new, "note": note}
        self._save()
        self._notify_entities()
        return True

    # ---------------------------------------------------------------- Bearbeiten (Panel)
    def get_entry(self, entry_id: str) -> dict | None:
        return next((e for e in self.data["entries"] if e["id"] == entry_id), None)

    def update_entry(self, entry_id: str, fields: dict) -> bool:
        e = self.get_entry(entry_id)
        if not e:
            return False
        for k in ("note", "station", "address", "item", "unit"):
            if k in fields:
                e[k] = str(fields[k] or "")
        for k in ("quantity", "unit_price", "total", "odometer"):
            if k in fields:
                e[k] = float(fields[k]) if fields[k] not in (None, "") else None
        if "odometer" in fields:
            e["odometer_source"] = "manuell" if e.get("odometer") is not None else None
        if self.phev and "energy" in fields and fields.get("kind") != "extra":   # Plug-in-Hybrid: Kraftstoff (l) oder Strom (kWh)
            if fields["energy"] == "electric":
                e["energy"] = "electric"
            else:
                e.pop("energy", None)
        if "kind" in fields:   # Art umstellen: Kraftstoff/Strom oder Zubehör (Verbrauchsmaterial)
            if fields["kind"] == "extra":
                e["kind"] = "extra"
                if not e.get("item"):
                    e["item"] = self.tr("Zubehör")
            else:
                for k in ("kind", "item", "unit"):
                    e.pop(k, None)
        if "quantity" in fields and fields["quantity"] not in (None, ""):
            e["quantity_source"] = "manuell"
        if "unit_price" in fields and fields["unit_price"] not in (None, ""):
            e["price_source"] = "manuell"
        if "charge_type" in fields:   # Ladeart von Hand: AC, DC oder leer (unbekannt)
            if fields["charge_type"] in ("ac", "dc") and e.get("kind") != "extra":
                e["charge_type"], e["charge_src"] = fields["charge_type"], "manuell"
            else:
                for k in ("charge_type", "charge_src"):
                    e.pop(k, None)
        if "fuel" in fields:   # Kraftstoffsorte (nur bei Tank-Einträgen)
            if fields["fuel"] in receipt.FUEL_GRADES and e.get("kind") != "extra" and e.get("energy") != "electric":
                e["fuel"] = fields["fuel"]
            else:
                e.pop("fuel", None)
        for n in fields.get("photos") or []:   # im Bearbeiten-Dialog aufgenommene, schon abgelegte Fotos
            if self._take_scanned(n) and n not in e["photos"]:
                e["photos"].append(n)
        if fields.get("ts"):   # Datum und Uhrzeit ändern
            e["ts"] = e["ts_start"] = float(fields["ts"])
            self.data["entries"].sort(key=lambda x: x["ts"])
        self._save()
        self._notify_entities()
        return True

    async def scan_photo(self, image: bytes, read: bool = True) -> dict:
        """Foto für den Dialog „Eintrag von Hand“ auslesen, ohne einen Eintrag anzulegen: liefert die gefundenen Werte und den Namen des abgelegten Fotos."""
        sent = None
        self._exif_pos = await self.hass.async_add_executor_job(receipt.exif_gps, image)
        taken = await self.hass.async_add_executor_job(receipt.exif_time, image)
        if taken:
            ts = dt_util.as_timestamp(taken.replace(tzinfo=dt_util.get_default_time_zone()))
            if ts <= time.time() + 3600:
                sent = ts
        image = await self.hass.async_add_executor_job(receipt.normalize, image)
        t0 = time.time()
        ai = await receipt.ai_read(self.hass, self._ai_entity(), image, self.media_dir, self._pos, self._exif_pos) if read else None   # read=False: Foto nur ablegen (die KI hat es schon vergeblich gelesen)
        if read and not ai and time.time() - t0 < 60:   # schneller Fehlschlag: einmal wiederholen
            await asyncio.sleep(3)
            ai = await receipt.ai_read(self.hass, self._ai_entity(), image, self.media_dir, self._pos, self._exif_pos)
        out: dict[str, Any] = {"found": False, "ts": sent}
        box = None
        if ai and ai.get("busy"):   # KI überlastet: Foto nicht ablegen, der Nutzer soll es später noch einmal versuchen
            return {"found": False, "busy": True}
        if ai and ai.get("error"):   # KI hat die Anfrage abgelehnt: dem Nutzer im Panel sagen
            return {"found": False, "ai_error": ai["error"]}
        if ai:
            km = ai.get("odometer")
            if km is not None and not self._km_sane(km):
                km = None
            d, hm = ai.get("date"), ai.get("time")
            when = dt_util.start_of_local_day(d).timestamp() + ((hm[0] * 3600 + hm[1] * 60) if hm else 12 * 3600) if d else sent
            if receipt.plausible(ai) or km is not None:
                box = ai.get("crop")
                out = {"note": self.currency_note(ai.get("orig")), "found": True, "quantity": ai.get("quantity"), "unit_price": ai.get("unit_price"), "total": ai.get("total"), "odometer": km,
                       "station": ai.get("station"), "address": ai.get("address"), "ts": when, "receipt": bool(receipt.plausible(ai)), "category": ai.get("category"), "item": ai.get("item"), "fuel_grade": ai.get("fuel_grade"), "ai_secs": ai.get("ai_secs")}
        name = await self.hass.async_add_executor_job(receipt.save_new_photo, image, box, self.photo_dir, ai if isinstance(ai, dict) else None, sent, None, self.orig_dir)
        issued = self.data.setdefault("scan_photos", [])
        issued.append(name)
        del issued[:-50]
        self._save(panel=False)
        out["photo"] = name
        return out

    def _take_scanned(self, name: object) -> bool:
        """Foto-Namen aus dem Panel nur annehmen, wenn scan_photo ihn selbst vergeben hat (einmalig; nie einen vom Browser erfundenen Pfad)."""
        issued = self.data.get("scan_photos") or []
        if not receipt.safe_photo_name(name) or name not in issued:
            return False
        issued.remove(name)
        return True

    async def discard_photo(self, name: str) -> None:
        """Noch keinem Eintrag zugeordnetes Foto (aus scan_photo) verwerfen."""
        if self._take_scanned(name) and not any(name in (e.get("photos") or []) for e in self.data["entries"]):
            await self._remove_files([name])
            self._save(panel=False)

    def add_manual(self, fields: dict) -> dict:
        e = self._new_manual_entry()
        for n in fields.get("photos") or []:   # vorher mit scan_photo abgelegte Fotos
            if self._take_scanned(n):
                e["photos"].append(n)
                e["receipt"] = True
        if fields.get("kind") == "extra":
            e["kind"] = "extra"
        if fields.get("ts"):
            e["ts"] = e["ts_start"] = float(fields["ts"])
        self.data["entries"].append(e)
        self.data["entries"].sort(key=lambda x: x["ts"])
        self.update_entry(e["id"], fields)
        if e.get("kind") == "extra":
            self._stamp_km(e)   # ohne eigenen Stand: der zuletzt bekannte
            self._save()
        return e

    async def _remove_files(self, names: list[str]) -> None:
        """Foto und gesichertes Original löschen (Namen werden geprüft, nur der Dateiname zählt)."""
        def _go() -> None:
            for n in names:
                if receipt.safe_photo_name(n):
                    (self.photo_dir / n).unlink(missing_ok=True)
                    (self.orig_dir / n).unlink(missing_ok=True)

        await self.hass.async_add_executor_job(_go)

    async def delete_entry(self, entry_id: str) -> bool:
        e = self.get_entry(entry_id)
        if not e:
            return False
        self.data["entries"].remove(e)
        await self._remove_files(list(e.get("photos", [])))
        await self.hass.async_add_executor_job(lambda: (self.curve_dir / f"{entry_id}.json").unlink(missing_ok=True))
        self._save()
        self._notify_entities()
        return True

    async def delete_photo(self, entry_id: str, name: str) -> bool:
        """Einen einzelnen Beleg bzw. ein Zusatzfoto löschen. Ohne Foto gilt der Eintrag wieder als „Beleg fehlt“."""
        e = self.get_entry(entry_id)
        if not e or name not in e.get("photos", []):
            return False
        e["photos"].remove(name)
        if not e["photos"]:
            e["receipt"] = False
        await self._remove_files([name])
        self._save()
        self._notify_entities()
        return True

    # ---------------------------------------------------------------- Auswertung
    def entries_with_stats(self) -> list[dict]:
        """Einträge mit Verbrauch je 100 km (Voll-zu-Voll, ab 30 % Zuwachs gilt eine Betankung als voll, siehe stats.py)."""
        es = stats.add_consumption(self.data["entries"])
        flags = stats.plausibility(es, self.capacity, self.capacity_el, self.phev, self.electric)
        for e in es:
            ack = e.get("ack") or {}   # quittierte Warnungen: nur ausgeblendet, solange der Hinweis genau derselbe ist (ändert sich ein Wert, erscheint er wieder)
            e["warn"] = {c: h for c, h in (flags.get(e["id"]) or {}).items() if ack.get(c) != self._warn_sig(h)}   # Warndreiecke in der Liste
        return es

    @staticmethod
    def _warn_sig(hint: dict) -> str:
        return json.dumps(hint, sort_keys=True, default=str)

    def ack_warning(self, entry_id: str, col: str) -> bool:
        """Warnung (Dreieck oder Fragezeichen) eines Eintrags quittieren. Alle Spalten mit demselben Hinweis werden mit quittiert (z. B. Menge, Preis und Betrag bei „doppelt“)."""
        e = self.get_entry(entry_id)
        if e is None:
            return False
        es = stats.add_consumption(self.data["entries"])
        raw = stats.plausibility(es, self.capacity, self.capacity_el, self.phev, self.electric).get(entry_id) or {}
        if col not in raw:
            return False
        sig = self._warn_sig(raw[col])
        ack = e.setdefault("ack", {})
        for c, h in raw.items():
            if self._warn_sig(h) == sig:
                ack[c] = sig
        self._save()
        self._notify_entities()
        return True
    def summary(self) -> dict[str, Any]:
        es = self.entries_with_stats()
        cons = [e["consumption"] for e in es if e["consumption"] and stats.energy_of(e) != "electric"][-5:]
        cons_el = [e["consumption"] for e in es if e["consumption"] and stats.energy_of(e) == "electric"][-5:]   # nur Plug-in-Hybrid
        year_ago = time.time() - 365 * 86400
        fuel = [e for e in es if e.get("kind") != "extra"]
        return {
            "last": fuel[-1] if fuel else None,
            "extras_12m": round(sum(e.get("total") or 0 for e in es if e.get("kind") == "extra" and e["ts"] >= year_ago), 2),
            "avg_consumption": round(sum(cons) / len(cons), 2) if cons else None,
            "avg_consumption_electric": round(sum(cons_el) / len(cons_el), 2) if cons_el else None,
            "cost_12m": round(sum(e.get("total") or 0 for e in es if e["ts"] >= year_ago), 2),
            "count": len(es),
            "correction": self.correction(),
            "live": self.live(),
            "status": "idle" if not any(d.pending for d in self._detectors()) else ("refuelling" if self._valid_pending() else "candidate"),
        }

    def numbers(self) -> dict[str, int]:
        """Laufende Nummer der Tankvorgänge (ältester = 1); Zubehör bekommt keine Nummer."""
        fuel = sorted((e for e in self.data["entries"] if e.get("kind") != "extra"), key=lambda x: x["ts"])
        return {e["id"]: i + 1 for i, e in enumerate(fuel)}

    def to_csv(self) -> str:
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        w.writerow([self.tr(f) for f in ["nr"] + CSV_FIELDS])
        numbers = self.numbers()

        def n(v, d=2):
            return "" if v is None else self._dec(f"{v:.{d}f}")

        for e in self.entries_with_stats():
            t = dt_util.as_local(dt_util.utc_from_timestamp(e["ts"]))
            w.writerow([numbers.get(e["id"], ""), self.name, self.plate, self.tr("Zubehör") if e.get("kind") == "extra" else (self.tr("Strom") if (self.electric or e.get("energy") == "electric") else self.tr("Kraftstoff")), e.get("item") or "", t.strftime("%d.%m.%Y"), t.strftime("%H:%M"), n(e.get("odometer"), 0), e.get("station") or "", e.get("address") or "", n(e.get("lat"), 6), n(e.get("lon"), 6), n(e.get("level_from"), 0), n(e.get("level_to"), 0), n(e.get("quantity")), (e.get("unit") or "") if e.get("kind") == "extra" else self.unit, n(e.get("unit_price"), 3), n(e.get("total")), e.get("quantity_source") or "", e.get("price_source") or "", "ja" if e.get("receipt") else "nein", n(e.get("consumption")), e.get("note") or ""])
        return buf.getvalue()

    # ---------------------------------------------------------------- Speichern
    def _save(self, panel: bool = True) -> None:
        if panel:
            self._panel("changed")
        self.store.async_delay_save(self._store_data, 2)

    def _store_data(self) -> dict:
        """Daten zum Speichern; der laufende Vorgang wird erst hier abgezogen, damit auch beim Herunterfahren der neueste Stand (Füllstand, letzter Anstieg) gesichert wird."""
        self.data["pending"] = self.detector.dump()
        self.data["pending_el"] = self.detector_el.dump() if self.detector_el else None
        self.data["wb_run"] = list(self._wb_run) if self._wb_run else None   # Wallbox liefert seit …: sonst geht die Zeile „Lädt gerade“ beim Neustart oder Neukonfigurieren verloren
        self.data["wb_log"] = [list(x) for x in list(self._wb.s)[-40:]]
        return self.data

    def _notify_entities(self) -> None:
        async_dispatcher_send(self.hass, signal(self.entry.entry_id))

    def _panel(self, event: str, **data: Any) -> None:
        """Dem offenen Panel melden, was gerade passiert (processing, reply, changed). Ohne offenes Panel kostet das nichts."""
        async_dispatcher_send(self.hass, PANEL_SIGNAL, {"event": event, "vehicle": self.entry.entry_id, **data})
