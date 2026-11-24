"""Senden über die Kanäle WhatsApp, Telegram und Companion-App (auch für den Test mit noch ungespeicherten Eingaben)."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from . import messages, whatsapp
from .const import CONF_NOTIFY, CONF_QUICK_LINK, CONF_TG_CHAT, CONF_TG_TOKEN, CONF_WA_PHONE
from .telegram import get_bot

LABELS = {"whatsapp": "WhatsApp", "telegram": "Telegram", "companion": "Companion-App"}


def test_text(name: str, channel: str, lang: str | None = None) -> str:
    return messages.tr(lang, "✅ Testnachricht von Drive Energy Doc ({0}): {1} funktioniert.", name, LABELS[channel])


async def send(hass: HomeAssistant, name: str, entry_key: str, o: dict, cfg: dict, channel: str, text: str, quick: bool = False) -> tuple[bool, str]:
    """Nachricht über einen Kanal senden. ``o`` sind die Fahrzeugwerte, ``cfg`` die globalen Einstellungen. Rückgabe (Erfolg, Fehlertext)."""
    if channel == "whatsapp":
        if not o.get(CONF_WA_PHONE):
            return False, messages.tr(hass.config.language, "Keine WhatsApp-Nummer eingetragen")
        return await whatsapp.send(hass, cfg, whatsapp.norm_phone(o[CONF_WA_PHONE]), text)
    if channel == "telegram":
        if not (o.get(CONF_TG_TOKEN) and o.get(CONF_TG_CHAT)):
            return False, messages.tr(hass.config.language, "Bot-Token und Chat-ID eintragen")
        return await get_bot(hass, o[CONF_TG_TOKEN]).send(o[CONF_TG_CHAT], text)
    svc = o.get(CONF_NOTIFY) or ""
    if "." not in svc:
        return False, messages.tr(hass.config.language, "Kein Benachrichtigungsdienst gewählt")
    dom, svc_name = svc.split(".", 1)
    if not hass.services.has_service(dom, svc_name):
        return False, messages.tr(hass.config.language, "Dienst {0} nicht gefunden (ist die Companion-App auf dem Handy angemeldet?)", svc)
    payload = {"message": text, "title": f"Drive Energy Doc {name}"}
    if svc_name.startswith("mobile_app_"):
        link = f"/drive-energy-doc?quick={entry_key}" if quick and entry_key and o.get(CONF_QUICK_LINK, True) else "/drive-energy-doc"   # quick: Antippen öffnet gleich die Aufnahme (Kamera/Galerie) für dieses Fahrzeug
        payload["data"] = {"url": link, "clickAction": link, "tag": f"drive_energy_doc_{entry_key or name}"}
    try:
        await hass.services.async_call(dom, svc_name, payload, blocking=True)
    except Exception as err:  # noqa: BLE001
        return False, str(err) or err.__class__.__name__
    return True, ""
