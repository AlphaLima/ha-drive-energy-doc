"""Minimaler Telegram-Client per Bot-API (Long Polling). Ein Poller je Bot-Token, Verteilung je Chat-ID.

Bewusst eigenständig und ohne Home-Assistants telegram_bot-Integration: Jedes Fahrzeug kann
einen eigenen Bot oder einen eigenen Chat (auch Gruppe) haben. Ein Token darf nur von EINEM Programm
abgefragt werden: nicht gleichzeitig in Node-RED oder telegram_bot benutzen (sonst Fehler 409).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiohttp import ClientError, ClientTimeout

from . import messages

_LOGGER = logging.getLogger(__name__)
API = "https://api.telegram.org"

Handler = Callable[[dict[str, Any]], Awaitable[None]]


class TelegramBot:
    def __init__(self, hass, session, token: str) -> None:
        self.hass, self.session, self.token = hass, session, token
        self.handlers: dict[str, Handler] = {}
        self._task: asyncio.Task | None = None
        self._offset = 0
        self._hinted: dict[str, float] = {}

    async def _call(self, method: str, **params) -> Any:
        async with self.session.post(f"{API}/bot{self.token}/{method}", json=params, timeout=ClientTimeout(total=70)) as resp:
            data = await resp.json(content_type=None)
        if not data.get("ok"):
            raise ClientError(data.get("description", "Telegram-Fehler"))
        return data["result"]

    async def send(self, chat_id: str, text: str) -> tuple[bool, str]:
        try:
            await self._call("sendMessage", chat_id=chat_id, text=text)
            return True, ""
        except (ClientError, TimeoutError) as err:
            _LOGGER.warning("Telegram senden fehlgeschlagen: %s", err)
            return False, str(err) or "Telegram nicht erreichbar"

    async def download(self, file_id: str) -> bytes | None:
        try:
            info = await self._call("getFile", file_id=file_id)
            async with self.session.get(f"{API}/file/bot{self.token}/{info['file_path']}", timeout=ClientTimeout(total=60)) as resp:
                return await resp.read() if resp.status == 200 else None
        except (ClientError, TimeoutError) as err:
            _LOGGER.warning("Telegram-Download fehlgeschlagen: %s", err)
            return None

    async def _unknown(self, chat: str, text: str) -> None:
        """Nachricht einer Chat-ID, die keinem Fahrzeug gehört: im Log vermerken und (höchstens alle 10 Minuten) die ID nennen."""
        _LOGGER.warning("Telegram: Nachricht von Chat-ID %s ignoriert, sie ist keinem Fahrzeug zugeordnet", chat)
        now = time.monotonic()
        if text.startswith("/start") or now - self._hinted.get(chat, -1e9) > 600:
            self._hinted[chat] = now
            await self.send(
                chat,
                messages.tr(self.hass.config.language, "Diese Chat-ID ({0}) ist noch keinem Fahrzeug zugeordnet, deshalb habe ich die Nachricht nicht verarbeitet.", chat)
                + "\n\n"
                + messages.tr(self.hass.config.language, "Trage die Zahl in Home Assistant ein: Einstellungen → Geräte & Dienste → Drive Energy Doc → Fahrzeug → Optionen → Kommunikation → Telegram → Chat-ID. Danach nehme ich Belege an."),
            )

    def add(self, chat_id: str, handler: Handler) -> None:
        self.handlers[str(chat_id)] = handler
        if self._task is None or self._task.done():
            self._task = self.hass.async_create_background_task(self._poll(), "drive_energy_doc_telegram")

    def remove(self, chat_id: str) -> None:
        self.handlers.pop(str(chat_id), None)
        if not self.handlers and self._task:
            self._task.cancel()
            self._task = None

    async def _poll(self) -> None:
        # Webhook würde Polling blockieren
        try:
            await self._call("deleteWebhook", drop_pending_updates=False)
        except (ClientError, TimeoutError):
            pass
        delay = 5
        while True:
            try:
                updates = await self._call("getUpdates", offset=self._offset, timeout=50, allowed_updates=["message"])
                delay = 5
            except asyncio.CancelledError:
                raise
            except (ClientError, TimeoutError) as err:
                _LOGGER.warning("Telegram-Abfrage fehlgeschlagen (%s), neuer Versuch in %s s", err, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 120)
                continue
            for upd in updates:
                self._offset = upd["update_id"] + 1
                msg = upd.get("message")
                if not msg:
                    continue
                chat = str(msg["chat"]["id"])
                handler = self.handlers.get(chat)
                try:
                    if handler:
                        await handler(msg)
                    else:
                        await self._unknown(chat, msg.get("text") or "")
                except Exception:  # noqa: BLE001 - eine Nachricht darf den Poller nicht beenden
                    _LOGGER.exception("Fehler bei Telegram-Nachricht")


def get_bot(hass, token: str) -> TelegramBot:
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    bots = hass.data.setdefault("drive_energy_doc_telegram", {})
    if token not in bots:
        bots[token] = TelegramBot(hass, async_get_clientsession(hass), token)
    return bots[token]
