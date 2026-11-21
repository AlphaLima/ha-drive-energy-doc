"""WhatsApp über die offizielle Cloud API von Meta.

Eingang: Webhook /api/drive_energy_doc/whatsapp (Meta ruft ihn an, muss aus dem Internet per HTTPS erreichbar sein).
Ausgang: Graph-API. Außerhalb des 24-Stunden-Fensters erlaubt WhatsApp nur freigegebene Vorlagen:
Dafür eine Vorlage mit genau einer Variable {{1}} in Meta anlegen und ihren Namen in den Einstellungen eintragen.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import re
import time
from typing import Any

from aiohttp import ClientError, ClientTimeout, web

from homeassistant.components.http import HomeAssistantView
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)
GRAPH = "https://graph.facebook.com/v21.0"
WINDOW_S = 23 * 3600
SEEN_MAX = 500


def norm_phone(number: str | None) -> str:
    return re.sub(r"\D", "", number or "")


def hub(hass) -> dict[str, Any]:
    return hass.data.setdefault("drive_energy_doc_wa", {"routes": {}, "last_in": {}, "seen": []})


async def send(hass, cfg: dict, to: str, text: str) -> tuple[bool, str]:
    """Text senden; falls das 24-h-Fenster zu ist, mit Vorlage. Rückgabe (Erfolg, Fehlertext)."""
    token, phone_id = cfg.get("wa_token"), cfg.get("wa_phone_id")
    if not (token and phone_id and to):
        return False, "WhatsApp-Zugang unvollständig (Token, Telefonnummern-ID oder Nummer des Fahrers fehlt)"
    session = async_get_clientsession(hass)
    template = cfg.get("wa_template")
    window_open = time.time() - hub(hass)["last_in"].get(to, 0) < WINDOW_S

    async def post(payload: dict) -> tuple[bool, int | None, str]:
        try:
            async with session.post(f"{GRAPH}/{phone_id}/messages", json={"messaging_product": "whatsapp", "to": to, **payload},
                                    headers={"Authorization": f"Bearer {token}"}, timeout=ClientTimeout(total=30)) as r:
                if r.status < 300:
                    return True, None, ""
                err = (await r.json(content_type=None)).get("error", {})
                _LOGGER.warning("WhatsApp senden: %s", err.get("message"))
                return False, err.get("code"), str(err.get("message") or f"HTTP {r.status}")
        except (ClientError, TimeoutError, ValueError) as e:
            _LOGGER.warning("WhatsApp senden fehlgeschlagen: %s", e)
            return False, None, str(e) or "WhatsApp nicht erreichbar"

    def tpl() -> dict:
        flat = re.sub(r"\s*\n+\s*", " | ", text).replace("\t", " ")
        flat = re.sub(r" {4,}", "   ", flat)
        return {"type": "template", "template": {"name": template, "language": {"code": cfg.get("wa_lang") or "de"},
                                                  "components": [{"type": "body", "parameters": [{"type": "text", "text": flat[:1000]}]}]}}

    if window_open or not template:
        ok, code, msg = await post({"type": "text", "text": {"body": text}})
        if not ok and code == 131047 and template:  # Fenster doch abgelaufen
            ok, code, msg = await post(tpl())
    else:
        ok, code, msg = await post(tpl())
    if ok:
        return True, ""
    if code == 131047:
        msg = "Das 24-Stunden-Fenster ist zu: schreib dem Bot zuerst eine Nachricht oder lege in den Einstellungen eine Vorlage an. " + msg
    return False, msg


async def check(hass, cfg: dict) -> tuple[bool, str]:
    """Zugangsdaten gegen die Graph-API prüfen (nichts zu prüfen = in Ordnung)."""
    token, phone_id = cfg.get("wa_token"), cfg.get("wa_phone_id")
    if not (token and phone_id):
        return True, ""
    try:
        async with async_get_clientsession(hass).get(f"{GRAPH}/{phone_id}", params={"fields": "display_phone_number"},
                                                      headers={"Authorization": f"Bearer {token}"}, timeout=ClientTimeout(total=20)) as r:
            data = await r.json(content_type=None)
        if r.status < 300:
            return True, ""
        return False, str((data.get("error") or {}).get("message") or f"HTTP {r.status}")
    except (ClientError, TimeoutError, ValueError) as e:
        return False, str(e) or "Meta nicht erreichbar"


async def download(hass, cfg: dict, media_id: str) -> bytes | None:
    token = cfg.get("wa_token")
    session = async_get_clientsession(hass)
    h = {"Authorization": f"Bearer {token}"}
    try:
        async with session.get(f"{GRAPH}/{media_id}", headers=h, timeout=ClientTimeout(total=30)) as r:
            url = (await r.json(content_type=None)).get("url")
        if not url:
            return None
        async with session.get(url, headers=h, timeout=ClientTimeout(total=60)) as r:
            return await r.read() if r.status == 200 else None
    except (ClientError, TimeoutError, ValueError) as e:
        _LOGGER.warning("WhatsApp-Download fehlgeschlagen: %s", e)
        return None


class WhatsAppView(HomeAssistantView):
    url = "/api/drive_energy_doc/whatsapp"
    name = "api:drive_energy_doc:whatsapp"
    requires_auth = False  # Meta kennt kein HA-Login; Schutz durch Verify-Token und Signatur

    async def get(self, request: web.Request) -> web.Response:
        from .vehicle import get_settings

        cfg = get_settings(request.app["hass"])
        q = request.query
        if q.get("hub.mode") == "subscribe" and cfg.get("wa_verify") and hmac.compare_digest(q.get("hub.verify_token", ""), cfg["wa_verify"]):
            return web.Response(text=q.get("hub.challenge", ""))
        return web.Response(status=403)

    async def post(self, request: web.Request) -> web.Response:
        from .vehicle import get_settings

        hass = request.app["hass"]
        cfg = get_settings(hass)
        raw = await request.read()
        secret = cfg.get("wa_secret")
        if not secret:  # ohne App-Secret kann die Herkunft nicht geprüft werden: nichts verarbeiten
            return web.Response(status=403)
        sig = request.headers.get("X-Hub-Signature-256", "")
        good = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, good):
            return web.Response(status=403)
        try:
            data = json.loads(raw)
        except ValueError:
            return web.Response(status=400)
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                for msg in (change.get("value") or {}).get("messages", []):
                    hass.async_create_background_task(_dispatch(hass, cfg, msg), "drive_energy_doc_wa_msg")
        return web.Response(text="ok")  # schnell antworten, sonst wiederholt Meta


def _ts(msg: dict) -> float | None:
    try:
        return float(msg.get("timestamp")) or None
    except (TypeError, ValueError):
        return None


async def _dispatch(hass, cfg: dict, msg: dict) -> None:
    h = hub(hass)
    if msg.get("id") in h["seen"]:
        return
    h["seen"] = (h["seen"] + [msg.get("id")])[-SEEN_MAX:]
    sender = norm_phone(msg.get("from"))
    vehicle = h["routes"].get(sender)
    if vehicle is None:
        _LOGGER.debug("WhatsApp-Nachricht von unbekannter Nummer ignoriert")
        return
    h["last_in"][sender] = time.time()
    try:
        kind = msg.get("type")
        if kind == "text":
            await vehicle.receive_text((msg.get("text") or {}).get("body", ""), sent_ts=_ts(msg))
        elif kind in ("image", "document"):
            media = msg.get(kind) or {}
            if kind == "document" and not str(media.get("mime_type", "")).startswith("image/"):
                return
            image = await download(hass, cfg, media["id"])
            if image:
                await vehicle.receive_photo(image, media.get("caption") or "", sent_ts=_ts(msg))
            else:
                await vehicle._say("Das Foto konnte ich nicht laden.")
    except Exception:  # noqa: BLE001 - eine Nachricht darf nichts blockieren
        _LOGGER.exception("Fehler bei WhatsApp-Nachricht")
