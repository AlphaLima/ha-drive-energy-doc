"""Ein Fahrzeug: Zustand, Tankerkennung, Preis, Beleg-Dialog und Speicherung."""

from __future__ import annotations

import asyncio
import csv
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
from . import messages, receipt, stats
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
        self.capacity = float(o.get(CONF_CAPACITY) or 0)
        self.store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")
        self.data: dict[str, Any] = {"entries": [], "pending": None, "awaiting": None}
        self.detector = FuelDetector(
            min_increase=float(o.get(CONF_MIN_INCREASE, DEFAULT_MIN_INCREASE)),
            settle_seconds=float(o.get(CONF_SETTLE) or (DEFAULT_SETTLE_ELECTRIC if self.electric else DEFAULT_SETTLE_FUEL)),
            min_distance=float(o.get(CONF_MIN_DISTANCE, DEFAULT_MIN_DISTANCE)),
            require_distance=bool(o.get(CONF_REQUIRE_DISTANCE, not self.electric)),
        )
        self._pos: tuple[float, float] | None = None
        self._capture: list[str] | None = None
        self._upload_lock = asyncio.Lock()
        self._batch: set[str] | None = None   # Stapel-Upload aus dem Panel: Plausibilitätsprüfung erst am Ende (batch_finish)
        self._unsubs: list = []
        self.photo_dir = Path(hass.config.path(DOMAIN, entry.entry_id, "photos"))
        self.orig_dir = Path(hass.config.path(DOMAIN, entry.entry_id, "originals"))
        self.media_dir = Path((hass.config.media_dirs or {}).get("local") or hass.config.path("media"))

    # ---------------------------------------------------------------- Lebenszyklus
    async def async_setup(self) -> None:
        saved = await self.store.async_load() or {}
        self.data.update(saved)
        if not self.data["entries"]:
            await self.hass.async_add_executor_job(self._import_folder)
        self.detector.pending = FuelDetector(pending=self.data.get("pending")).pending
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
            if e.get("odometer") is not None and e.get("odometer_source") != "manuell" and e.get("kind") != "extra" and not self._km_sane(e["odometer"], e["id"]):
                _LOGGER.info("Unmöglicher Kilometerstand %s im Eintrag %s entfernt (%s)", e["odometer"], e["id"], self.name)
                e["odometer"] = None
                e["odometer_source"] = None
        self._save()
        self._pos = self._read_pos()
        lvl = self._read_float(o.get(CONF_LEVEL))
        if lvl is not None:
            self.detector.prev_level = lvl
        tracked = [e for e in (o.get(CONF_LEVEL), o.get(CONF_TRACKER)) if e]
        self._unsubs.append(async_track_state_change_event(self.hass, tracked, self._state_changed))
        self._unsubs.append(async_track_time_interval(self.hass, self._tick, CHECK_EVERY))
        if o.get(CONF_TG_TOKEN) and o.get(CONF_TG_CHAT):
            get_bot(self.hass, o[CONF_TG_TOKEN]).add(o[CONF_TG_CHAT], self.handle_message)
        if o.get(CONF_WA_PHONE):
            whatsapp.hub(self.hass)["routes"][whatsapp.norm_phone(o[CONF_WA_PHONE])] = self

    def _import_folder(self) -> None:
        """Einmaliger Import: config/drive_energy_doc/import/<Fahrzeugname>/entries.json (+ photos/, originals/). Läuft im Executor."""
        import json
        import shutil

        src = Path(self.hass.config.path(DOMAIN, "import", self.name))
        f = src / "entries.json"
        if not f.is_file():
            return
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

    async def async_unload(self) -> None:
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
        level = self._read_float(entity)
        if level is None:
            return
        result = self.detector.on_level(level, time.time(), self._pos, self._read_float(self.o.get(CONF_ODOMETER)))
        if result in ("started", "valid", "cancelled"):
            self._save()
        if result == "valid":
            self.hass.async_create_task(self._fetch_price())
        self._notify_entities()

    @callback
    def _tick(self, _now) -> None:
        self._pos = self._read_pos() or self._pos
        done = self.detector.check(time.time(), self._pos)
        if done:
            self.hass.async_create_task(self._finish(done))
        else:
            self._notify_entities()

    def _ai_entity(self) -> str | None:
        """Gewählte KI-Aufgabe, sonst automatisch Gemini, sonst die erste vorhandene ai_task-Entität."""
        return get_settings(self.hass).get(CONF_AI_TASK) or default_ai_entity(self.hass)

    # ---------------------------------------------------------------- Preis
    async def _fetch_price(self, pending: dict | None = None) -> dict[str, Any]:
        """Preis/Station für den laufenden Vorgang holen (am Beginn gültiger Zuwachs, nicht erst beim Wegfahren)."""
        p = self.detector.pending
        target = p.extras if p else (pending or {})
        if self.electric:
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
    async def _finish(self, done: dict) -> None:
        ex = dict(done.get("extras") or {})
        if "unit_price" not in ex:
            ex = await self._fetch_price({**done, "pos": (done["lat"], done["lon"]), **ex}) or ex
        pct = done["level"] - done["start_level"]
        qty = round(pct / 100 * self.capacity, 2) if self.capacity else None
        entry = {
            "id": uuid.uuid4().hex[:12],
            "ts": done["last_increase_ts"],
            "ts_start": done["start_ts"],
            "odometer": done.get("odometer"),
            "lat": done.get("lat"),
            "lon": done.get("lon"),
            "station": ex.get("station"),
            "address": ex.get("address"),
            "station_id": ex.get("station_id"),
            "level_from": round(done["start_level"], 1),
            "level_to": round(done["level"], 1),
            "quantity": qty,
            "quantity_source": "berechnet",
            "unit_price": ex.get("unit_price"),
            "price_source": ex.get("price_source"),
            "total": None,
            "photos": [],
            "receipt": False,
            "note": "",
        }
        entry["total"] = round(qty * entry["unit_price"], 2) if qty and entry["unit_price"] else None
        entry["photos"].extend(ex.get("extra_photos", []))
        r = ex.get("receipt")
        if r:
            self._apply_values(entry, r["values"], r.get("photo"))
        od = ex.get("odometer")
        if od:
            entry["odometer"], entry["odometer_source"] = float(od["km"]), "foto"
            if od.get("photo"):
                entry["photos"].append(od["photo"])
        self.data["entries"].append(entry)
        self.data["pending"] = None
        self._save()
        self._notify_entities()
        self.hass.bus.async_fire(f"{DOMAIN}_refuel", {"vehicle": self.name, "entry": entry})
        if not r:
            await self._say(self._summary(entry, self.tr("Tankvorgang erkannt")) + "\n\n" + self.tr("Bitte schick mir den Beleg (Foto vom Bon oder der Zapfsäule) oder tippe: Menge Betrag, z. B. 45,93 105,13") + "\n" + self.tr("Zubehör gekauft (AdBlue, Öl, Scheibenwischer …)? Schreib: extra 24,90 oder x Öl 1 9,50 (auch als Bildtext zum Foto). Alle Kommandos: ? oder hilfe."))

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
        return ["km"] if live("unread_photo") and self._batch is None else []   # im Stapel nicht mitten drin fragen

    async def upload(self, image: bytes | None, text: str, batch: bool = False, finish: bool = False) -> list[str]:
        """Beleg aus dem Panel (Handykamera). Antworten kommen als Liste zurück statt per Messenger."""
        async with self._upload_lock:   # nacheinander: sonst überschreiben sich die Antwortlisten zweier gleichzeitiger Uploads
            if finish:
                return self.batch_finish()
            self._batch = (self._batch if self._batch is not None else set()) if batch else None
            return await self._upload_locked(image, text)

    def batch_finish(self) -> list[str]:
        """Ende eines Stapel-Uploads: jetzt, wo alle Fotos zugeordnet sind, die Einträge prüfen (Verbrauch) und Auffälligkeiten melden."""
        ids, self._batch = self._batch or set(), None
        out = []
        for e in sorted((x for x in (self.get_entry(i) for i in ids) if x), key=lambda x: x["ts"]):
            chk = stats.check_consumption(self.data["entries"], e, e["odometer"]) if e.get("odometer") is not None else None
            if chk and not chk["ok"]:
                when = dt_util.as_local(dt_util.utc_from_timestamp(e["ts"])).strftime("%d.%m.%Y")
                out.append(f"{when}: " + self.tr("⚠️ Verbrauch ungewöhnlich: {0} bei {1} km seit dem letzten Tanken (Durchschnitt {2}), bitte Kilometerstand prüfen.", self._cons_txt(chk["cons"]), self._fmt_km(chk["driven"]), self._cons_txt(chk["avg"])))
        up = self.data.get("unread_photo")
        if up and time.time() - up["ts"] < AWAIT_TTL:   # im Stapel unlesbar gebliebenes Foto: am Ende melden statt mittendrin zu fragen
            out.append(self.tr("Auf dem Foto konnte ich weder Beleg noch Kilometerstand lesen. Schick den Kilometerstand als Text, z. B. „km 61240“, dann lege ich den Eintrag mit dem Foto an."))
        return out

    async def _upload_locked(self, image: bytes | None, text: str) -> list[str]:
        self._capture = []
        try:
            if image:
                sent = None   # Aufnahmezeit aus dem Foto: so wird ein später hochgeladenes Tacho-Foto dem richtigen Tankvorgang zugeordnet
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
        out = []
        if self.o.get(CONF_WA_PHONE) and (not enabled or "whatsapp" in enabled):
            out.append("whatsapp")
        if self.o.get(CONF_TG_TOKEN) and self.o.get(CONF_TG_CHAT) and (not enabled or "telegram" in enabled):
            out.append("telegram")
        if self.o.get(CONF_NOTIFY) and (not enabled or "companion" in enabled):
            out.append("companion")
        return out

    async def send_channel(self, channel: str, text: str) -> tuple[bool, str]:
        return await chan.send(self.hass, self.name, self.entry.entry_id, self.o, get_settings(self.hass), channel, text)

    async def test_channel(self, channel: str) -> tuple[bool, str]:
        if channel not in self.channels():
            return False, self.tr("Dieser Kanal ist bei diesem Fahrzeug nicht eingerichtet")
        label = {"whatsapp": "WhatsApp", "telegram": "Telegram", "companion": self.tr("die Companion-App")}[channel]
        return await self.send_channel(channel, self.tr("✅ Testnachricht von Drive Energy Doc ({0}): {1} funktioniert.", self.name, label))

    async def _say(self, text: str) -> None:
        if self._capture is not None:
            self._capture.append(text)
            return
        for ch in self.channels():
            await self.send_channel(ch, text)

    def _summary(self, e: dict, head: str) -> str:
        when = dt_util.as_local(dt_util.utc_from_timestamp(e["ts"])).strftime("%d.%m.%Y %H:%M")
        extra = e.get("kind") == "extra"
        unit = (e.get("unit") or "") if extra else self.unit
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
        return "\n".join(lines)

    async def handle_message(self, msg: dict[str, Any]) -> None:
        text = (msg.get("text") or msg.get("caption") or "").strip()
        file_id = None
        if msg.get("photo"):
            file_id = msg["photo"][-1]["file_id"]
        elif (msg.get("document") or {}).get("mime_type", "").startswith("image/"):
            file_id = msg["document"]["file_id"]
        if file_id:
            image = await get_bot(self.hass, self.o[CONF_TG_TOKEN]).download(file_id)
            if image:
                await self.receive_photo(image, text)
            else:
                await self._say(self.tr("Das Foto konnte ich nicht laden."))
            return
        if text:
            await self.receive_text(text, sent_ts=msg.get("date"))

    async def _extra(self, item: str, rest: str, photo: str | None, values: dict | None = None) -> None:
        """Zubehör erfassen (AdBlue, Öl, Scheibenwischer …): Bezeichnung, optional Menge, Preis, Betrag, Foto.
        Ohne Zahlen wartet der Eintrag auf die nächste Nachricht mit Menge/Betrag."""
        values = values or receipt.parse_extra_values(rest)
        d = receipt.parse_date_hint(rest)
        entry = self._new_manual_entry()
        entry["kind"] = "extra"
        entry["item"] = item
        entry["unit"] = {v[0].lower(): v[1] for v in messages.items().values()}.get(item.lower(), "")
        if d:
            entry["ts"] = entry["ts_start"] = datetime.combine(d, dtime(12, 0), tzinfo=dt_util.DEFAULT_TIME_ZONE).timestamp()
        if values:
            self._apply_values(entry, values, photo)
        elif photo:
            entry["photos"].append(photo)
            entry["receipt"] = True
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
        image = await self.hass.async_add_executor_job(receipt.normalize, image)
        low = caption.lower().strip()
        px = receipt.parse_extra(caption)
        if px:
            item, rest = px
            values, box = receipt.parse_extra_values(rest), None
            if not values:
                ai = await receipt.ai_read(self.hass, self._ai_entity(), image, self.media_dir)
                if ai and receipt.plausible(ai):
                    values, box = ai, ai.get("crop")
            name = receipt.new_photo_name()
            await self.hass.async_add_executor_job(receipt.crop_and_save, image, box, self.photo_dir, name, self.orig_dir)
            return await self._extra(item, rest, name, values)
        extra = low.startswith(tuple(messages.keywords("photo")))
        values = None if extra else receipt.parse_text(caption)
        km = None if (extra or values) else receipt.parse_km(caption)   # Tacho-Foto mit Bildtext „km 54210“
        box = None
        if not extra and not values and km is None:
            t0 = time.time()
            ai = await receipt.ai_read(self.hass, self._ai_entity(), image, self.media_dir)
            if not ai and time.time() - t0 < 60:   # schneller Fehlschlag (z. B. Überlastung des KI-Dienstes): einmal wiederholen
                await asyncio.sleep(3)
                ai = await receipt.ai_read(self.hass, self._ai_entity(), image, self.media_dir)
            if ai and receipt.plausible(ai):
                values, box = ai, ai.get("crop")
            elif ai and ai.get("odometer") and self._km_sane(ai["odometer"], ts=sent_ts):   # mit bekannter Aufnahme-/Sendezeit gegen die Reihenfolge der Einträge prüfen
                km, box = float(ai["odometer"]), ai.get("crop")           # nur Kilometerstand erkannt: Foto vom Tacho
        name = receipt.new_photo_name()
        await self.hass.async_add_executor_job(receipt.crop_and_save, image, box, self.photo_dir, name, self.orig_dir)
        if km is not None:
            return await self._odometer(km, name, sent_ts)
        if extra or not values:
            d = receipt.parse_date_hint(caption)
            target = self._entry_on(d, True) if d else (self._newest_within(48 * 3600) or (self.data["entries"][-1] if self.data["entries"] else None))
            pend = self.detector.pending
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
                await self._say(self.tr("Auf dem Foto konnte ich weder Beleg noch Kilometerstand lesen. Schick den Kilometerstand als Text, z. B. „km 61240“, dann lege ich den Eintrag mit dem Foto an."))
            return
        await self._route(values, name)

    # ---------------------------------------------------------------- Kilometerstand (Tacho-Foto oder Text)
    @staticmethod
    def _fmt_km(km: float) -> str:
        return f"{km:,.0f}".replace(",", ".")

    async def _odometer(self, km: float, photo: str | None, sent_ts: float | None = None) -> None:
        """Kilometerstand dem Tankvorgang zuordnen, der zur Sendezeit passt (Foto oder Text)."""
        sent = sent_ts or time.time()
        pend = self.detector.pending
        if pend and pend.valid:  # es wird gerade getankt: beim Abschluss übernehmen
            pend.extras["odometer"] = {"km": km, "photo": photo}
            self._save()
            await self._say(self.tr("Kilometerstand {0} km vorgemerkt, er wird beim Abschluss des laufenden Tankvorgangs übernommen.", self._fmt_km(km)))
            return
        photo_only = not self.o.get(CONF_LEVEL)
        open_e = self._open_entry("odometer") if photo_only else None
        if open_e:
            sent = open_e["ts"]   # Beleg kam zuerst: der Kilometerstand gehört zu diesem Eintrag
        m = stats.match_odometer(self.data["entries"], km, sent)
        from_photo = photo is not None   # von der KI aus einem Foto gelesen (nicht getippt): im Zweifel weglassen statt nachfragen
        if photo_only and m["status"] in ("none", "too_old"):
            # reiner Foto-Betrieb: der Tacho kommt zuerst, der Beleg wird danach (bis 48 h) diesem Eintrag zugeordnet
            e = self._new_manual_entry()
            e["ts"] = e["ts_start"] = sent
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
        chk = stats.check_consumption(self.data["entries"], e, km)
        if chk and not chk["ok"] and from_photo:
            return await self._skip_km(e, km, photo, "Verbrauch unplausibel")
        if chk and not chk["ok"]:   # getippter Stand, Verbrauch passt nicht zu Tankmenge und Durchschnitt: nachfragen
            self.data["awaiting_odo"] = {"id": e["id"], "km": km, "photo": photo, "ts": time.time(), "confirm": True}
            self._save()
            why = self.tr("würde bei {0} km seit dem letzten Tanken {1} ergeben (Durchschnitt {2})", self._fmt_km(chk["driven"]), self._cons_txt(chk["cons"]), self._cons_txt(chk["avg"]))
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

    def _cons_txt(self, value: float) -> str:
        return self._dec(f"{value:.1f}") + f" {self.unit}/100 km"

    async def _apply_odometer(self, entry: dict, km: float, photo: str | None, dt: float) -> None:
        if self._batch is not None:
            self._batch.add(entry["id"])
        entry["odometer"] = float(km)
        entry["odometer_source"] = "foto" if photo else "manuell"
        if photo:
            entry["photos"].append(photo)
        self._save()
        self._notify_entities()
        when = dt_util.as_local(dt_util.utc_from_timestamp(entry["ts"])).strftime("%d.%m.%Y %H:%M")
        late = " " + self.tr("(Nachricht {0} h nach dem Tanken)" if dt > 0 else "(Nachricht {0} h vor dem Tanken)", self._dec(f"{abs(dt) / 3600:.1f}")) if abs(dt) > 3 * 3600 else ""
        await self._say(self.tr("Kilometerstand {0} km für den Tankvorgang vom {1} übernommen{2}.", self._fmt_km(km), when, late))

    # ---------------------------------------------------------------- Zuordnung
    def _entry_on(self, d, any_kind: bool = False) -> dict | None:
        hits = [e for e in self.data["entries"] if dt_util.as_local(dt_util.utc_from_timestamp(e["ts"])).date() == d and (any_kind or e.get("kind") != "extra")]
        return hits[-1] if hits else None

    def _newest_within(self, seconds: float) -> dict | None:
        for e in reversed(self.data["entries"]):
            if time.time() - e["ts"] <= seconds and not e.get("receipt") and e.get("kind") != "extra":
                return e
        return None

    def _new_manual_entry(self) -> dict:
        return {
            "id": uuid.uuid4().hex[:12], "created": time.time(), "ts": time.time(), "ts_start": time.time(), "odometer": self._read_float(self.o.get(CONF_ODOMETER)),
            "lat": self._pos[0] if self._pos else None, "lon": self._pos[1] if self._pos else None, "station": None, "address": None,
            "station_id": None, "level_from": None, "level_to": None, "quantity": None, "quantity_source": "manuell", "unit_price": None,
            "price_source": None, "total": None, "photos": [], "receipt": False, "note": "",
        }

    def _km_sane(self, km, exclude: str | None = None, ts: float | None = None) -> bool:
        """Von der KI gelesener Kilometerstand möglich? Siehe stats.km_plausible (mit Datum vom Beleg: Reihenfolge der Einträge, sonst Abstand zum Mittelwert)."""
        return stats.km_plausible(self.data["entries"], km, ts, exclude)

    def _entry_by_km(self, km: float, tolerance: float = 50.0) -> dict | None:
        """Eintrag ohne Beleg, dessen Kilometerstand (vom Tacho-Foto) fast genau zum Stand auf dem Beleg passt: so finden Beleg und Tacho auch bei gemischter Reihenfolge zusammen."""
        c = [e for e in self.data["entries"] if e.get("kind") != "extra" and not e.get("receipt") and e.get("quantity") is None and e.get("odometer") is not None and abs(e["odometer"] - km) <= tolerance]
        return min(c, key=lambda e: abs(e["odometer"] - km)) if c else None

    def _open_entry(self, need: str) -> dict | None:
        """Zuletzt angelegter Eintrag (der letzten Stunden), dem noch der Beleg ("receipt") bzw. der Kilometerstand ("odometer") fehlt.
        Damit gehören Tacho-Foto und Beleg zusammen, egal in welcher Reihenfolge sie kommen und welches Datum auf dem Beleg steht."""
        es = [e for e in self.data["entries"] if e.get("kind") != "extra" and e.get("created")]
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
            await self._say(self.tr("Zum Eintrag vom {0} ({1} km) fehlt noch der Beleg oder das Foto der Zapfsäule. Bitte schick es noch.", when, self._fmt_km(e.get("odometer") or 0)))

        self._unsubs.append(async_call_later(self.hass, delay, _cb))

    async def _route(self, values: dict, photo: str | None) -> None:
        d = values.get("date")
        if values.get("odometer"):   # Kilometerstand vom Beleg gegen die Reihenfolge der Einträge prüfen (Datum/Uhrzeit vom Beleg), unmöglicher Stand: ignorieren
            hm = values.get("time")
            when = (dt_util.start_of_local_day(d).timestamp() + ((hm[0] * 3600 + hm[1] * 60) if hm else 12 * 3600)) if d else time.time()
            if not self._km_sane(values["odometer"], ts=when):
                _LOGGER.info("Kilometerstand %s vom Beleg unplausibel, ignoriert (%s)", values["odometer"], self.name)
                values = {**values, "odometer": None}
        photo_only = not self.o.get(CONF_LEVEL)  # ohne Füllstandssensor: jeder Beleg ohne passenden Eintrag legt einen neuen an
        open_e = ((self._entry_by_km(values["odometer"]) if values.get("odometer") else None) or self._open_entry("receipt")) if photo_only else None
        if open_e:   # das Tacho-Foto kam zuerst und hat schon eine neue Zeile angelegt: der Beleg gehört dazu (Datum und Uhrzeit vom Beleg gelten)
            if d:
                hm = values.get("time")
                open_e["ts"] = open_e["ts_start"] = dt_util.start_of_local_day(d).timestamp() + ((hm[0] * 3600 + hm[1] * 60) if hm else 12 * 3600)
                self.data["entries"].sort(key=lambda x: x["ts"])
            await self._apply_and_report(open_e, values, photo)
            return
        if d:
            target = self._entry_on(d)
            if not target and photo_only:
                target = self._new_manual_entry()
                hm = values.get("time")
                target["ts"] = target["ts_start"] = dt_util.start_of_local_day(d).timestamp() + ((hm[0] * 3600 + hm[1] * 60) if hm else 12 * 3600)
                self.data["entries"].append(target)
                self.data["entries"].sort(key=lambda x: x["ts"])
            if not target:
                self.data["awaiting"] = {"values": {**values, "date": None}, "photo": photo, "ts": time.time()}
                await self._say(self.tr("Zu {0} gibt es keinen Tankvorgang. Antworte mit einem anderen Datum oder „neu“.", f"{d:%d.%m.%Y}"))
                return
        elif self.detector.pending and self.detector.pending.valid:
            self.detector.pending.extras["receipt"] = {"values": {k: v for k, v in values.items() if k != "date"}, "photo": photo}
            self._save()
            await self._say(self.tr("Beleg vorgemerkt, er wird beim Abschluss des laufenden Tankvorgangs übernommen."))
            return
        else:
            target = self._newest_within(48 * 3600)
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
            have = ", ".join(x for x in (self._dec(f"{target['quantity']:.2f}") + f" {self.unit}" if target.get("quantity") else "", self._dec(f"{target['total']:.2f}") + " €" if target.get("total") else "") if x)
            self.data["awaiting_overwrite"] = {"id": target["id"], "values": {k: (v if k != "date" else None) for k, v in values.items()}, "photo": photo, "ts": time.time()}
            self._save()
            key = "Dieser Beleg ist schon eingetragen (Eintrag vom {0}: {1}). Antworte „ja“, um ihn trotzdem zu überschreiben, oder „nein“." if same else "Es gibt schon einen Beleg-Eintrag vom {0} ({1}). Antworte „ja“, um ihn mit dem neuen Beleg zu überschreiben, oder „nein“."
            await self._say(self.tr(key, when, have))
            return
        await self._apply_and_report(target, values, photo)

    async def _apply_and_report(self, entry: dict, values: dict, photo: str | None) -> None:
        rkm = values.get("odometer")
        batch = self._batch is not None
        if batch:
            self._batch.add(entry["id"])
        if rkm:   # Kilometerstand vom Beleg nur übernehmen, wenn der Verbrauch dazu passt; im Zweifel weglassen (keine Rückfrage)
            self._apply_values(entry, {**values, "odometer": None}, photo)
            chk = stats.check_consumption(self.data["entries"], entry, float(rkm))
            if chk and not chk["ok"]:
                _LOGGER.info("Kilometerstand %s vom Beleg ausgelassen (Verbrauch unplausibel, %s)", rkm, self.name)
            else:
                entry["odometer"] = float(rkm)
        else:
            self._apply_values(entry, values, photo)
        self._save()
        self._notify_entities()
        warn = "" if receipt.plausible(entry) else "\n" + self.tr("⚠️ Menge × Preis passt nicht zum Betrag, bitte prüfen.")
        chk = stats.check_consumption(self.data["entries"], entry, entry["odometer"]) if entry.get("odometer") is not None and not batch else None
        if chk and not chk["ok"]:
            warn += "\n" + self.tr("⚠️ Verbrauch ungewöhnlich: {0} bei {1} km seit dem letzten Tanken (Durchschnitt {2}), bitte Kilometerstand prüfen.", self._cons_txt(chk["cons"]), self._fmt_km(chk["driven"]), self._cons_txt(chk["avg"]))
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
        if values.get("odometer"):
            entry["odometer"] = float(values["odometer"])  # Kilometerstand vom Beleg ist genauer als der beim Erkennen
        if q or p or t:
            entry["receipt"] = True
        if photo:
            entry["photos"].insert(0, photo)

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
        if "quantity" in fields and fields["quantity"] not in (None, ""):
            e["quantity_source"] = "manuell"
        if "unit_price" in fields and fields["unit_price"] not in (None, ""):
            e["price_source"] = "manuell"
        if fields.get("ts"):   # Datum und Uhrzeit ändern
            e["ts"] = e["ts_start"] = float(fields["ts"])
            self.data["entries"].sort(key=lambda x: x["ts"])
        self._save()
        self._notify_entities()
        return True

    def add_manual(self, fields: dict) -> dict:
        e = self._new_manual_entry()
        if fields.get("kind") == "extra":
            e["kind"] = "extra"
        if fields.get("ts"):
            e["ts"] = e["ts_start"] = float(fields["ts"])
        self.data["entries"].append(e)
        self.data["entries"].sort(key=lambda x: x["ts"])
        self.update_entry(e["id"], fields)
        return e

    async def _remove_files(self, names: list[str]) -> None:
        """Foto und gesichertes Original löschen (Namen werden geprüft, nur der Dateiname zählt)."""
        def _go() -> None:
            for n in names:
                if n and "/" not in n and "\\" not in n and ".." not in n:
                    (self.photo_dir / n).unlink(missing_ok=True)
                    (self.orig_dir / n).unlink(missing_ok=True)

        await self.hass.async_add_executor_job(_go)

    async def delete_entry(self, entry_id: str) -> bool:
        e = self.get_entry(entry_id)
        if not e:
            return False
        self.data["entries"].remove(e)
        await self._remove_files(list(e.get("photos", [])))
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
        return stats.add_consumption(self.data["entries"])

    def summary(self) -> dict[str, Any]:
        es = self.entries_with_stats()
        cons = [e["consumption"] for e in es if e["consumption"]][-5:]
        year_ago = time.time() - 365 * 86400
        fuel = [e for e in es if e.get("kind") != "extra"]
        return {
            "last": fuel[-1] if fuel else None,
            "extras_12m": round(sum(e.get("total") or 0 for e in es if e.get("kind") == "extra" and e["ts"] >= year_ago), 2),
            "avg_consumption": round(sum(cons) / len(cons), 2) if cons else None,
            "cost_12m": round(sum(e.get("total") or 0 for e in es if e["ts"] >= year_ago), 2),
            "count": len(es),
            "status": "idle" if not self.detector.pending else ("refuelling" if self.detector.pending.valid else "candidate"),
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
            w.writerow([numbers.get(e["id"], ""), self.name, self.plate, self.tr("Zubehör") if e.get("kind") == "extra" else (self.tr("Strom") if self.electric else self.tr("Kraftstoff")), e.get("item") or "", t.strftime("%d.%m.%Y"), t.strftime("%H:%M"), n(e.get("odometer"), 0), e.get("station") or "", e.get("address") or "", n(e.get("lat"), 6), n(e.get("lon"), 6), n(e.get("level_from"), 0), n(e.get("level_to"), 0), n(e.get("quantity")), (e.get("unit") or "") if e.get("kind") == "extra" else self.unit, n(e.get("unit_price"), 3), n(e.get("total")), e.get("quantity_source") or "", e.get("price_source") or "", "ja" if e.get("receipt") else "nein", n(e.get("consumption")), e.get("note") or ""])
        return buf.getvalue()

    # ---------------------------------------------------------------- Speichern
    def _save(self) -> None:
        self.data["pending"] = self.detector.dump()
        self.store.async_delay_save(lambda: self.data, 2)

    def _notify_entities(self) -> None:
        async_dispatcher_send(self.hass, signal(self.entry.entry_id))
