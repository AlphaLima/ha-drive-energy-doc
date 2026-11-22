"""Drive Energy Doc: Fahrtenbuch/Drive Energy Doc für beliebig viele Fahrzeuge (Verbrenner und Elektro)."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from pathlib import Path

import re

import voluptuous as vol
from aiohttp import web

from homeassistant.components import frontend, panel_custom, websocket_api
from homeassistant.components.http import HomeAssistantView, StaticPathConfig
from homeassistant.components.http.auth import async_sign_path
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.loader import async_get_integration

from .const import CONF_KIND, CONF_PLATE, CONF_PLATE_COUNTRY, DOMAIN, KIND_SETTINGS, PANEL_PATH, PANEL_URL, PLATE_CODES, PLATE_NAMES
from . import messages, plate
from .vehicle import Vehicle

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["sensor"]


def _vehicles(hass: HomeAssistant) -> dict[str, Vehicle]:
    return hass.data.setdefault(DOMAIN, {}).setdefault("vehicles", {})


def _vehicle(hass: HomeAssistant, entry_id: str) -> Vehicle:
    v = _vehicles(hass).get(entry_id)
    if v is None:
        raise HomeAssistantError("Fahrzeug nicht gefunden")
    return v


CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config) -> bool:
    await hass.async_add_executor_job(messages.preload)  # Sprachdateien einmalig lesen
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if entry.data.get(CONF_KIND) == KIND_SETTINGS:
        return True  # globale Einstellungen werden bei Bedarf live gelesen, kein Neuladen der Fahrzeuge nötig
    vehicle = Vehicle(hass, entry)
    await vehicle.async_setup()
    _vehicles(hass)[entry.entry_id] = vehicle
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_reload))
    await _register_once(hass)
    return True


async def _reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if entry.data.get(CONF_KIND) == KIND_SETTINGS:
        return True
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        v = _vehicles(hass).pop(entry.entry_id, None)
        if v:
            await v.async_unload()
            await v.store.async_save(v.data)
    return ok


async def _register_once(hass: HomeAssistant) -> None:
    root = hass.data[DOMAIN]
    if root.get("registered"):
        return
    root["registered"] = True
    frontend_dir = Path(__file__).parent / "frontend"
    await hass.http.async_register_static_paths([StaticPathConfig("/drive_energy_doc_static", str(frontend_dir), False)])
    version = (await async_get_integration(hass, DOMAIN)).version
    try:
        await panel_custom.async_register_panel(
            hass,
            webcomponent_name="drive-energy-doc-panel",
            frontend_url_path=PANEL_PATH,
            sidebar_title="Drive Energy Doc",
            sidebar_icon="mdi:gas-station",
            module_url=f"{PANEL_URL}?v={version}",
            embed_iframe=False,
            require_admin=False,
        )
    except ValueError:
        pass
    hass.http.register_view(PhotoView)
    hass.http.register_view(CsvView)
    hass.http.register_view(PlateView)
    hass.http.register_view(VehicleImageView)
    hass.http.register_view(UploadView)
    from .whatsapp import WhatsAppView

    hass.http.register_view(WhatsAppView)
    for cmd in (ws_list, ws_update, ws_delete, ws_add, ws_delete_photo, ws_countries, ws_set_plate):
        websocket_api.async_register_command(hass, cmd)

    async def export_csv(call: ServiceCall) -> None:
        v = _vehicle(hass, call.data["config_entry"])
        path = Path(hass.config.path(DOMAIN, f"{v.name}.csv"))
        await hass.async_add_executor_job(lambda: (path.parent.mkdir(parents=True, exist_ok=True), path.write_text(v.to_csv(), encoding="utf-8-sig")))

    async def submit_text(call: ServiceCall) -> None:
        v = _vehicle(hass, call.data["config_entry"])
        await v.receive_text(call.data["text"])

    async def test_message(call: ServiceCall) -> None:
        v = _vehicle(hass, call.data["config_entry"])
        for ch in [call.data["channel"]] if call.data.get("channel") else v.channels():
            ok, detail = await v.test_channel(ch)
            if not ok:
                raise HomeAssistantError(f"{ch}: {detail}")

    hass.services.async_register(DOMAIN, "test_message", test_message, vol.Schema({vol.Required("config_entry"): str, vol.Optional("channel"): vol.In(["whatsapp", "telegram", "companion"])}))
    hass.services.async_register(DOMAIN, "export_csv", export_csv, vol.Schema({vol.Required("config_entry"): str}))
    hass.services.async_register(DOMAIN, "submit_text", submit_text, vol.Schema({vol.Required("config_entry"): str, vol.Required("text"): str}))


def _signed(hass: HomeAssistant, path: str, minutes: int = 60) -> str:
    return async_sign_path(hass, path, timedelta(minutes=minutes))


class PhotoView(HomeAssistantView):
    url = "/api/drive_energy_doc/photo/{entry_id}/{name}"
    name = "api:drive_energy_doc:photo"
    requires_auth = True

    async def get(self, request: web.Request, entry_id: str, name: str) -> web.StreamResponse:
        hass = request.app["hass"]
        v = _vehicles(hass).get(entry_id)
        if v is None or "/" in name or "\\" in name or ".." in name:
            return web.Response(status=404)
        path = v.photo_dir / name
        if not await hass.async_add_executor_job(path.is_file):
            return web.Response(status=404)
        return web.FileResponse(path, headers={"Cache-Control": "private, max-age=86400"})


class UploadView(HomeAssistantView):
    """Beleg-Foto oder Text aus dem Panel (auch Companion-App): multipart mit Feldern file und text."""

    url = "/api/drive_energy_doc/upload/{entry_id}"
    name = "api:drive_energy_doc:upload"
    requires_auth = True

    async def post(self, request: web.Request, entry_id: str) -> web.Response:
        v = _vehicles(request.app["hass"]).get(entry_id)
        if v is None:
            return web.Response(status=404)
        image, text = None, ""
        reader = await request.multipart()
        async for part in reader:
            if part.name == "file":
                chunks, size = [], 0
                while chunk := await part.read_chunk(1 << 20):
                    size += len(chunk)
                    if size > 20 * 1024 * 1024:
                        return web.Response(status=413)
                    chunks.append(chunk)
                image = b"".join(chunks) or None
            elif part.name == "text":
                text = (await part.text())[:500]
        # als eigene Aufgabe laufen lassen: bricht der Browser die Verbindung ab (Netz, Seitenwechsel), wird der Beleg trotzdem fertig verarbeitet
        task = request.app["hass"].async_create_task(v.upload(image, text))
        replies = await asyncio.shield(task)
        return self.json({"replies": replies, "awaiting": bool(v.data.get("awaiting"))})


class VehicleImageView(HomeAssistantView):
    url = "/api/drive_energy_doc/vehicle_image/{name}"
    name = "api:drive_energy_doc:vehicle_image"
    requires_auth = True

    async def get(self, request: web.Request, name: str) -> web.StreamResponse:
        hass = request.app["hass"]
        if not re.fullmatch(r"[0-9a-f]{32}\.(jpg|png)", name):
            return web.Response(status=404)
        path = Path(hass.config.path(DOMAIN, "images", name))
        if not await hass.async_add_executor_job(path.is_file):
            return web.Response(status=404)
        return web.FileResponse(path, headers={"Cache-Control": "private, max-age=3600"})


class PlateView(HomeAssistantView):
    """Kennzeichen-Vorschau als SVG für die Dialoge. Text wird gefiltert, nichts aus den Fahrzeugdaten wird gelesen."""

    url = "/api/drive_energy_doc/plate.svg"
    name = "api:drive_energy_doc:plate"
    requires_auth = False

    async def get(self, request: web.Request) -> web.Response:
        cc = request.query.get("cc", "DE").upper()
        if cc not in PLATE_CODES:
            cc = "DE"
        return web.Response(
            text=plate.svg(PLATE_CODES[cc], cc, request.query.get("t", "")),
            content_type="image/svg+xml",
            headers={"Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'", "Cache-Control": "no-store"},
        )


class CsvView(HomeAssistantView):
    url = "/api/drive_energy_doc/export/{entry_id}"
    name = "api:drive_energy_doc:export"
    requires_auth = True

    async def get(self, request: web.Request, entry_id: str) -> web.StreamResponse:
        v = _vehicles(request.app["hass"]).get(entry_id)
        if v is None:
            return web.Response(status=404)
        body = "﻿" + v.to_csv()  # BOM: Excel erkennt UTF-8
        return web.Response(body=body.encode("utf-8"), content_type="text/csv", charset="utf-8", headers={"Content-Disposition": f'attachment; filename="drive_energy_doc_{v.name}.csv"'})


@websocket_api.websocket_command({vol.Required("type"): "drive_energy_doc/list"})
@websocket_api.async_response
async def ws_list(hass, connection, msg) -> None:
    out = []
    for eid, v in _vehicles(hass).items():
        entries = v.entries_with_stats()
        for e in entries:
            e["photo_urls"] = [_signed(hass, f"/api/drive_energy_doc/photo/{eid}/{n}") for n in e.get("photos", [])]
        out.append({"id": eid, "name": v.name, "image": v.image_entity(), "image_url": _signed(hass, f"/api/drive_energy_doc/vehicle_image/{v.image_file}") if v.image_file else None, "plate": v.plate, "type": v.vehicle_type(), "plate_country": v.plate_country(), "plate_code": PLATE_CODES.get(v.plate_country(), "D"), "unit": v.unit, "energy": v.energy, "summary": {**v.summary(), "last": None}, "entries": list(reversed(entries)), "csv_url": _signed(hass, f"/api/drive_energy_doc/export/{eid}", 10)})
    connection.send_result(msg["id"], out)


@websocket_api.websocket_command({vol.Required("type"): "drive_energy_doc/update", vol.Required("vehicle"): str, vol.Required("entry"): str, vol.Required("fields"): dict})
@websocket_api.async_response
async def ws_update(hass, connection, msg) -> None:
    connection.send_result(msg["id"], _vehicle(hass, msg["vehicle"]).update_entry(msg["entry"], msg["fields"]))


@websocket_api.websocket_command({vol.Required("type"): "drive_energy_doc/delete", vol.Required("vehicle"): str, vol.Required("entry"): str})
@websocket_api.async_response
async def ws_delete(hass, connection, msg) -> None:
    connection.send_result(msg["id"], await _vehicle(hass, msg["vehicle"]).delete_entry(msg["entry"]))


@websocket_api.websocket_command({vol.Required("type"): "drive_energy_doc/add", vol.Required("vehicle"): str, vol.Required("fields"): dict})
@websocket_api.async_response
async def ws_add(hass, connection, msg) -> None:
    e = _vehicle(hass, msg["vehicle"]).add_manual(msg["fields"])
    connection.send_result(msg["id"], e["id"])


@websocket_api.websocket_command({vol.Required("type"): "drive_energy_doc/delete_photo", vol.Required("vehicle"): str, vol.Required("entry"): str, vol.Required("photo"): str})
@websocket_api.async_response
async def ws_delete_photo(hass, connection, msg) -> None:
    connection.send_result(msg["id"], await _vehicle(hass, msg["vehicle"]).delete_photo(msg["entry"], msg["photo"]))


@websocket_api.websocket_command({vol.Required("type"): "drive_energy_doc/countries"})
@websocket_api.async_response
async def ws_countries(hass, connection, msg) -> None:
    """Länderliste für den Kennzeichen-Dialog (Kürzel, Name, Beispiel)."""
    connection.send_result(msg["id"], [{"cc": cc, "code": code, "name": PLATE_NAMES.get(cc, cc), "example": plate.EXAMPLES.get(cc, "")} for cc, code in PLATE_CODES.items()])


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): "drive_energy_doc/set_plate", vol.Required("vehicle"): str, vol.Required("plate"): str, vol.Required("country"): vol.In(list(PLATE_CODES))})
@websocket_api.async_response
async def ws_set_plate(hass, connection, msg) -> None:
    """Kennzeichen und Land eines Fahrzeugs speichern (nur Administratoren)."""
    entry = hass.config_entries.async_get_entry(msg["vehicle"])
    if entry is None or entry.domain != DOMAIN:
        connection.send_error(msg["id"], "not_found", "Fahrzeug nicht gefunden")
        return
    opts = dict(entry.options)
    text = plate.clean_text(msg["plate"])
    if text:
        opts[CONF_PLATE] = text
    else:
        opts.pop(CONF_PLATE, None)
    opts[CONF_PLATE_COUNTRY] = msg["country"]
    hass.config_entries.async_update_entry(entry, options=opts)
    connection.send_result(msg["id"], True)
