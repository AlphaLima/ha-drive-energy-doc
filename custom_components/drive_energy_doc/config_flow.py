"""Geführte Einrichtung: erst globale Einstellungen (Kanäle, Preisquelle, KI), dann je Fahrzeug.

Gefragt wird nur, was zur gewählten Kommunikation passt (Telegram, WhatsApp, Companion-App).
Erkennungsschwellen stehen nur in den Optionen, Standardwerte passen für die meisten Fahrzeuge.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector as sel

from .const import *  # noqa: F403
from aiohttp import ClientError, ClientTimeout

from homeassistant.helpers.aiohttp_client import async_get_clientsession

import re

from homeassistant.data_entry_flow import section

from . import channels as chan
from . import plate, receipt, whatsapp
from .vehicle import default_ai_entity, get_settings

CHANNELS = ["whatsapp", "telegram", "companion"]
WA_FIELDS = ["wa_token", "wa_phone_id", "wa_verify", "wa_secret", "wa_template", "wa_lang"]


def _num(unit=None, mn=0, mx=100000, step="any"):
    return sel.NumberSelector(sel.NumberSelectorConfig(min=mn, max=mx, step=step, mode="box", unit_of_measurement=unit))


def _text(key, d, **kw):
    return vol.Optional(key, description={"suggested_value": d.get(key, kw.get("default"))})


def _ent(domains):
    return sel.EntitySelector(sel.EntitySelectorConfig(domain=domains))


def _clean(d: dict) -> dict:
    return {k: v for k, v in d.items() if v not in ("", None)}


def _merge(current: dict, user_input: dict, schema: vol.Schema) -> dict:
    """Optionen zusammenführen; ein im Formular geleertes Feld wird entfernt."""
    out = {k: v for k, v in current.items() if k not in {str(m) for m in schema.schema}}
    out.update(_clean(user_input))
    return out


def notify_options(hass: HomeAssistant) -> list[str]:
    svcs = hass.services.async_services().get("notify", {})
    return [f"notify.{n}" for n in sorted(n for n in svcs if n.startswith("mobile_app_"))]


# ---------------------------------------------------------------- Schemas
def s_settings(d: dict, hass: HomeAssistant) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_CHANNELS, default=d.get(CONF_CHANNELS, ["companion"])): sel.SelectSelector(sel.SelectSelectorConfig(options=CHANNELS, multiple=True, translation_key="channels")),
            vol.Required(CONF_PRICE_PROVIDER, default=d.get(CONF_PRICE_PROVIDER, "auto")): sel.SelectSelector(sel.SelectSelectorConfig(options=["auto", "none", "tankerkoenig", "econtrol_at", "prix_fr"], translation_key="provider")),
            _text(CONF_EL_PRICE, d): str,
            _text(CONF_AI_TASK, d, default=default_ai_entity(hass)): _ent(["ai_task"]),
        }
    )


def s_price_key(d: dict) -> vol.Schema:
    return vol.Schema({_text(CONF_TK_KEY, d): str})


def s_whatsapp(d: dict) -> vol.Schema:
    return vol.Schema({_text(k, d, default="de" if k == "wa_lang" else None): str for k in WA_FIELDS})


def s_basic(d: dict, hass_country: str | None = None) -> vol.Schema:
    default_cc = (hass_country or "DE").upper()
    default_cc = default_cc if default_cc in PLATE_COUNTRIES else "DE"
    return vol.Schema(
        {
            # Pflicht: nur Name, Antriebsart und Tank-/Akkugröße. Die Sensoren sind optional:
            # ohne sie wird nichts automatisch erkannt, Einträge kommen dann nur per Foto/Text/Panel.
            vol.Required(CONF_NAME, default=d.get(CONF_NAME, "")): str,
            vol.Required(CONF_ENERGY, default=d.get(CONF_ENERGY, "diesel")): sel.SelectSelector(sel.SelectSelectorConfig(options=["diesel", "e5", "e10", "electric"], translation_key="energy")),
            vol.Required(CONF_CAPACITY, default=d.get(CONF_CAPACITY, 50)): _num("l / kWh", 1, 500),
            _text(CONF_LEVEL, d): _ent(["sensor", "number"]),
            _text(CONF_ODOMETER, d): _ent(["sensor", "number"]),
            _text(CONF_TRACKER, d): _ent(["device_tracker"]),
            # Optional (nur Aussehen): Kennzeichen, Land, Typ, Bild
            _text(CONF_PLATE, d): str,
            vol.Optional(CONF_PLATE_COUNTRY, description={"suggested_value": d.get(CONF_PLATE_COUNTRY, default_cc)}): _country_selector(),
            _text(CONF_VEHICLE_TYPE, d): str,
            _text(CONF_LANGUAGE, d): _language_selector(),
            _text(CONF_IMAGE, d): _ent(["image", "camera"]),
            vol.Optional("image_upload"): sel.FileSelector(sel.FileSelectorConfig(accept="image/*")),
            **({vol.Optional("image_remove", default=False): bool} if d.get(CONF_IMAGE_FILE) else {}),
        }
    )


SECTION_FIELDS = {"whatsapp": [CONF_WA_PHONE], "telegram": [CONF_TG_TOKEN, CONF_TG_CHAT], "companion": [CONF_NOTIFY]}


def s_messaging(d: dict, channels: list[str], hass: HomeAssistant) -> vol.Schema:
    """Je Kanal eine Gruppe mit eigenen Feldern und einem Schalter „Testnachricht senden“. WhatsApp steht oben."""
    test = lambda: vol.Optional("test", default=False)  # noqa: E731
    toggle = sel.BooleanSelector()
    f: dict = {}
    if "whatsapp" in channels:
        f[vol.Required("whatsapp")] = section(vol.Schema({_text(CONF_WA_PHONE, d): str, test(): toggle}), {"collapsed": False})
    if "telegram" in channels:
        f[vol.Required("telegram")] = section(vol.Schema({_text(CONF_TG_TOKEN, d): str, _text(CONF_TG_CHAT, d): str, test(): toggle}), {"collapsed": False})
    if "companion" in channels:
        notify = sel.SelectSelector(sel.SelectSelectorConfig(options=notify_options(hass), custom_value=True, mode=sel.SelectSelectorMode.DROPDOWN))
        f[vol.Required("companion")] = section(vol.Schema({_text(CONF_NOTIFY, d): notify, test(): toggle}), {"collapsed": False})
    return vol.Schema(f)


def flatten_messaging(user_input: dict) -> tuple[dict, list[str]]:
    """Gruppen auflösen: Werte der Felder und die Kanäle, deren Test angehakt ist (Reihenfolge WhatsApp, Telegram, Companion)."""
    flat, tests = {}, []
    for name, fields in SECTION_FIELDS.items():
        part = user_input.get(name)
        if part is None:
            continue
        for key in fields:
            flat[key] = part.get(key)
        if part.get("test"):
            tests.append(name)
    return flat, tests


def _notify_result(hass: HomeAssistant, name: str, text: str) -> None:
    from homeassistant.components import persistent_notification

    persistent_notification.async_create(hass, text, title=f"Drive Energy Doc: Testergebnis ({name})", notification_id="drive_energy_doc_test")


async def run_tests(hass: HomeAssistant, name: str, o: dict, tests: list[str]) -> str:
    """Testnachrichten mit den eingegebenen (noch nicht gespeicherten) Werten senden; Ergebnis als Markdown."""
    cfg = get_settings(hass)
    lines = []
    for ch in tests:
        ok, detail = await chan.send(hass, name, "", o, cfg, ch, chan.test_text(name, ch))
        lines.append(f"{'✅' if ok else '❌'} **{chan.LABELS[ch]}**: " + ("Testnachricht gesendet. Ist sie angekommen?" if ok else detail))
        if ch == "whatsapp" and ok:
            last = whatsapp.hub(hass)["last_in"].get(whatsapp.norm_phone(o.get(CONF_WA_PHONE)))
            when = datetime.fromtimestamp(last).strftime("%d.%m.%Y %H:%M") if last else "noch nie"
            lines.append(f"WhatsApp-Eingang zuletzt empfangen: {when}. Antworte kurz auf die Testnachricht, dann siehst du beim nächsten Test, ob der Webhook ankommt.")
    result = "\n\n".join(lines)
    _notify_result(hass, name, result)
    return result


class _MessagingMixin:
    """Gemeinsamer Ablauf für Einrichtung und Optionen: Formular mit Gruppen, optional Test, Ergebnis, Speichern."""

    _draft: dict | None = None
    _result: str = ""
    _tests: list[str] = []

    def _msg_base(self) -> dict:
        raise NotImplementedError

    def _msg_name(self) -> str:
        raise NotImplementedError

    async def _msg_finish(self, flat: dict):
        raise NotImplementedError

    async def _msg_step(self, user_input):
        channels = get_settings(self.hass).get(CONF_CHANNELS) or CHANNELS
        d = {**self._msg_base(), **(self._draft or {})}
        errors, detail = {}, ""
        if user_input is not None:
            flat, tests = flatten_messaging(user_input)
            ok, detail = await check_telegram(self.hass, flat.get(CONF_TG_TOKEN))
            if ok:
                self._draft = flat
                if tests:
                    self._tests = tests
                    self._result = await run_tests(self.hass, self._msg_name(), {**self._msg_base(), **flat}, tests)
                    return await self.async_step_messaging_result()
                return await self._msg_finish(flat)
            errors = {"base": "tg_invalid"}
            d = {**d, **flat}
        return self.async_show_form(step_id="messaging", data_schema=s_messaging(d, channels, self.hass), errors=errors, description_placeholders={"detail": detail})

    async def async_step_messaging_result(self, user_input=None):
        """Ergebnis der Testnachrichten mit Buttons: Speichern, nochmal senden, zurück zum Formular."""
        return self.async_show_menu(step_id="messaging_result", menu_options=["msg_save", "msg_again", "msg_back"], description_placeholders={"result": self._result})

    async def async_step_msg_save(self, user_input=None):
        return await self._msg_finish(self._draft or {})

    async def async_step_msg_again(self, user_input=None):
        self._result = await run_tests(self.hass, self._msg_name(), {**self._msg_base(), **(self._draft or {})}, self._tests)
        return await self.async_step_messaging_result()

    async def async_step_msg_back(self, user_input=None):
        return await self._msg_step(None)  # Eingaben bleiben stehen


def s_thresholds(d: dict) -> vol.Schema:
    electric = d.get(CONF_ENERGY) == "electric"
    return vol.Schema(
        {
            vol.Optional(CONF_MIN_INCREASE, default=d.get(CONF_MIN_INCREASE, DEFAULT_MIN_INCREASE)): _num("%", 1, 50),
            vol.Optional(CONF_SETTLE, default=d.get(CONF_SETTLE, DEFAULT_SETTLE_ELECTRIC if electric else DEFAULT_SETTLE_FUEL)): _num("s", 10, 7200, 1),
            vol.Optional(CONF_MIN_DISTANCE, default=d.get(CONF_MIN_DISTANCE, DEFAULT_MIN_DISTANCE)): _num("m", 20, 5000, 1),
            vol.Optional(CONF_REQUIRE_DISTANCE, default=d.get(CONF_REQUIRE_DISTANCE, not electric)): bool,
        }
    )


async def check_telegram(hass: HomeAssistant, token: str | None) -> tuple[bool, str]:
    if not token:
        return True, ""
    try:
        async with async_get_clientsession(hass).get(f"https://api.telegram.org/bot{token}/getMe", timeout=ClientTimeout(total=15)) as r:
            data = await r.json(content_type=None)
        return (True, "") if data.get("ok") else (False, str(data.get("description") or "Token ungültig"))
    except (ClientError, TimeoutError, ValueError) as e:
        return False, str(e) or "Telegram nicht erreichbar"


async def process_image(hass: HomeAssistant, user_input: dict, old_file: str | None) -> tuple[dict, bool]:
    """Upload-Feld auswerten: neues Bild speichern (altes löschen) bzw. entfernen. Rückgabe (bereinigte Eingabe, Bild entfernt)."""
    from pathlib import Path

    from homeassistant.components.file_upload import process_uploaded_file

    data = dict(user_input)
    file_id = data.pop("image_upload", None)
    remove = bool(data.pop("image_remove", False))
    folder = Path(hass.config.path(DOMAIN, "images"))

    def _drop(name: str | None) -> None:
        if name and re.fullmatch(r"[0-9a-f]{32}\.(jpg|png)", name):
            (folder / name).unlink(missing_ok=True)

    if file_id:
        def _store() -> str:
            with process_uploaded_file(hass, file_id) as path:
                return receipt.save_vehicle_image(Path(path).read_bytes(), folder)

        data[CONF_IMAGE_FILE] = await hass.async_add_executor_job(_store)
        await hass.async_add_executor_job(_drop, old_file)
        return data, False
    if remove:
        await hass.async_add_executor_job(_drop, old_file)
    return data, remove


def _country_selector() -> sel.SelectSelector:
    # Optionen mit eigenen Namen (keine Übersetzungsschlüssel: Großbuchstaben-Kürzel sind dort nicht erlaubt)
    opts = [{"value": c, "label": PLATE_NAMES.get(c, c)} for c in PLATE_COUNTRIES]
    return sel.SelectSelector(sel.SelectSelectorConfig(options=opts, mode=sel.SelectSelectorMode.DROPDOWN, sort=True))


def _language_selector() -> sel.SelectSelector:
    """Sprache der Bot-Antworten dieses Fahrzeugs (leer = Sprache von Home Assistant); Namen in der jeweiligen Sprache."""
    from . import messages

    opts = [{"value": c, "label": LANG_NAMES.get(c, c)} for c in messages.languages()]
    return sel.SelectSelector(sel.SelectSelectorConfig(options=opts, mode=sel.SelectSelectorMode.DROPDOWN, sort=True))


def plate_md(d: dict, hass_country: str | None) -> str:
    """Markdown-Bild mit dem Kennzeichen, wie es im Panel aussehen wird."""
    from urllib.parse import quote

    cc = str(d.get(CONF_PLATE_COUNTRY) or hass_country or "DE").upper()
    cc = cc if cc in PLATE_CODES else "DE"
    text = d.get(CONF_PLATE) or plate.EXAMPLES.get(cc, "")
    return f"![Kennzeichen](/api/drive_energy_doc/plate.svg?cc={cc}&t={quote(str(text))})"


def needs_key(hass: HomeAssistant, provider: str) -> bool:
    return provider == "tankerkoenig" or (provider == "auto" and (hass.config.country or "").upper() == "DE")


# ---------------------------------------------------------------- Einrichtung
class DriveEnergyDocConfigFlow(_MessagingMixin, ConfigFlow, domain=DOMAIN):  # noqa: F405
    VERSION = 1

    def __init__(self) -> None:
        self._data: dict = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return DriveEnergyDocOptionsFlow()

    def _has_settings(self) -> bool:
        return any(e.data.get(CONF_KIND) == KIND_SETTINGS for e in self._async_current_entries())

    async def _read_seed(self) -> list | None:
        path = Path(self.hass.config.path(DOMAIN, "seed.json"))

        def _load():
            if not path.is_file():
                return None
            data = json.loads(path.read_text(encoding="utf-8"))
            path.unlink()  # enthält Schlüssel: nach dem Lesen löschen
            return data

        return await self.hass.async_add_executor_job(_load)

    async def async_step_user(self, user_input=None) -> ConfigFlowResult:
        seed = await self._read_seed()
        if seed:  # vorbereitete Einrichtung (Migration): ohne Eingabe anlegen
            settings = next((i for i in seed if i.get(CONF_KIND) == KIND_SETTINGS), None)
            for item in (i for i in seed if i.get(CONF_KIND) == KIND_VEHICLE):
                self.hass.async_create_task(self.hass.config_entries.flow.async_init(DOMAIN, context={"source": "import"}, data=item))
            if settings and not self._has_settings():
                await self.async_set_unique_id("drive_energy_doc_settings")
                return self.async_create_entry(title="Drive Energy Doc Einstellungen", data=settings)
            return self.async_abort(reason="seed_done")
        if not self._has_settings():
            return await self.async_step_settings()
        return await self.async_step_vehicle()

    async def async_step_import(self, data) -> ConfigFlowResult:
        self._async_abort_entries_match({CONF_NAME: data[CONF_NAME]})
        return self.async_create_entry(title=data[CONF_NAME], data=data)

    # --- Globale Einstellungen
    async def async_step_settings(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            self._data = {CONF_KIND: KIND_SETTINGS, **_clean(user_input)}
            if needs_key(self.hass, user_input[CONF_PRICE_PROVIDER]):
                return await self.async_step_price_key()
            return await self._after_price()
        return self.async_show_form(step_id="settings", data_schema=s_settings({}, self.hass))

    async def async_step_price_key(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(_clean(user_input))
            return await self._after_price()
        return self.async_show_form(step_id="price_key", data_schema=s_price_key({}))

    async def _after_price(self) -> ConfigFlowResult:
        if "whatsapp" in self._data.get(CONF_CHANNELS, []):
            return await self.async_step_whatsapp()
        return await self._create_settings()

    async def async_step_whatsapp(self, user_input=None) -> ConfigFlowResult:
        errors, detail = {}, ""
        if user_input is not None:
            ok, detail = await whatsapp.check(self.hass, user_input)
            if ok:
                self._data.update(_clean(user_input))
                return await self._create_settings()
            errors = {"base": "wa_invalid"}
        return self.async_show_form(step_id="whatsapp", data_schema=self.add_suggested_values_to_schema(s_whatsapp({}), user_input or {}), errors=errors, description_placeholders={"detail": detail})

    async def _create_settings(self) -> ConfigFlowResult:
        await self.async_set_unique_id("drive_energy_doc_settings")
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title="Drive Energy Doc Einstellungen", data=self._data)

    # --- Fahrzeug
    async def async_step_vehicle(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            self._async_abort_entries_match({CONF_NAME: user_input[CONF_NAME]})
            self._vehicle_ui = user_input
            return await self.async_step_plate_preview()
        prefill = getattr(self, "_vehicle_ui", None) or {}
        schema = s_basic({}, self.hass.config.country)
        if prefill:  # zurück aus der Vorschau: Eingaben bleiben stehen
            schema = self.add_suggested_values_to_schema(schema, prefill)
        return self.async_show_form(step_id="vehicle", data_schema=schema, description_placeholders={"plate_preview": plate_md(prefill, self.hass.config.country)})

    async def async_step_plate_preview(self, user_input=None) -> ConfigFlowResult:
        """Das gezeichnete Kennzeichen mit dem gewählten Land zeigen, bevor das Fahrzeug angelegt wird."""
        ui = self._vehicle_ui
        if user_input is not None:
            if not user_input.get("ok"):
                return await self.async_step_vehicle()
            ui, _ = await process_image(self.hass, ui, None)
            self._data = {CONF_KIND: KIND_VEHICLE, **_clean(ui)}
            if get_settings(self.hass).get(CONF_CHANNELS):
                return await self.async_step_messaging()
            return self.async_create_entry(title=self._data[CONF_NAME], data=self._data)
        return self.async_show_form(step_id="plate_preview", data_schema=vol.Schema({vol.Required("ok", default=True): bool}), description_placeholders={"plate_preview": plate_md(ui, self.hass.config.country)})

    def _msg_base(self) -> dict:
        return self._data

    def _msg_name(self) -> str:
        return self._data.get(CONF_NAME, "")

    async def _msg_finish(self, flat: dict) -> ConfigFlowResult:
        self._data.update(_clean(flat))
        return self.async_create_entry(title=self._data[CONF_NAME], data=self._data)

    async def async_step_messaging(self, user_input=None) -> ConfigFlowResult:
        return await self._msg_step(user_input)


# ---------------------------------------------------------------- Optionen
class DriveEnergyDocOptionsFlow(_MessagingMixin, OptionsFlow):
    def _cur(self) -> dict:
        return {**self.config_entry.data, **self.config_entry.options}

    async def async_step_init(self, user_input=None) -> ConfigFlowResult:
        if self._cur().get(CONF_KIND) == KIND_SETTINGS:
            return self.async_show_menu(step_id="init", menu_options=["whatsapp", "general", "price_key"])
        return self.async_show_menu(step_id="init", menu_options=["basic", "messaging", "thresholds"])

    async def _form(self, step: str, schema: vol.Schema, user_input, check=None) -> ConfigFlowResult:
        errors, detail = {}, ""
        if user_input is not None:
            drop_image = False
            if step == "basic":
                self._basic_ui = user_input          # erst die Vorschau des Schilds, gespeichert wird danach
                return await self.async_step_plate_preview()
            ok, detail = await check(user_input) if check else (True, "")
            if ok:
                out = _merge(dict(self.config_entry.options), user_input, schema)
                if drop_image:
                    out.pop(CONF_IMAGE_FILE, None)
                return self.async_create_entry(data=out)
            errors = {"base": "wa_invalid" if step == "whatsapp" else "tg_invalid"}
            schema = self.add_suggested_values_to_schema(schema, user_input)
        placeholders = {"detail": detail}
        if step == "basic":
            placeholders["plate_preview"] = plate_md({**self._cur(), **(getattr(self, "_basic_ui", None) or {})}, self.hass.config.country)
        return self.async_show_form(step_id=step, data_schema=schema, errors=errors, description_placeholders=placeholders)

    async def async_step_general(self, user_input=None) -> ConfigFlowResult:
        return await self._form("general", s_settings(self._cur(), self.hass), user_input)

    async def async_step_price_key(self, user_input=None) -> ConfigFlowResult:
        return await self._form("price_key", s_price_key(self._cur()), user_input)

    async def async_step_whatsapp(self, user_input=None) -> ConfigFlowResult:
        return await self._form("whatsapp", s_whatsapp(self._cur()), user_input, lambda d: whatsapp.check(self.hass, d))

    async def async_step_basic(self, user_input=None) -> ConfigFlowResult:
        schema = s_basic(self._cur(), self.hass.config.country)
        if user_input is None and getattr(self, "_basic_ui", None):  # zurück aus der Vorschau: Eingaben bleiben stehen
            schema = self.add_suggested_values_to_schema(schema, self._basic_ui)
        return await self._form("basic", schema, user_input)

    async def async_step_plate_preview(self, user_input=None) -> ConfigFlowResult:
        """Das gezeichnete Kennzeichen mit dem gewählten Land zeigen, bevor die Fahrzeugdaten gespeichert werden."""
        ui = self._basic_ui
        if user_input is not None:
            if not user_input.get("ok"):
                return await self.async_step_basic()
            ui, drop_image = await process_image(self.hass, ui, self._cur().get(CONF_IMAGE_FILE))
            out = _merge(dict(self.config_entry.options), ui, s_basic(self._cur(), self.hass.config.country))
            if drop_image:
                out.pop(CONF_IMAGE_FILE, None)
            return self.async_create_entry(data=out)
        return self.async_show_form(step_id="plate_preview", data_schema=vol.Schema({vol.Required("ok", default=True): bool}), description_placeholders={"plate_preview": plate_md({**self._cur(), **ui}, self.hass.config.country)})

    def _msg_base(self) -> dict:
        return self._cur()

    def _msg_name(self) -> str:
        return self._cur().get(CONF_NAME, "")

    async def _msg_finish(self, flat: dict) -> ConfigFlowResult:
        keys = {k for fields in SECTION_FIELDS.values() for k in fields}
        out = {k: v for k, v in dict(self.config_entry.options).items() if k not in keys}
        out.update(_clean(flat))
        return self.async_create_entry(data=out)

    async def async_step_messaging(self, user_input=None) -> ConfigFlowResult:
        return await self._msg_step(user_input)

    async def async_step_thresholds(self, user_input=None) -> ConfigFlowResult:
        return await self._form("thresholds", s_thresholds(self._cur()), user_input)
