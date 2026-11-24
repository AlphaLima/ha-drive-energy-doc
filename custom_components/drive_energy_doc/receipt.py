"""Beleg-Auswertung: Textweg ohne KI, KI-Weg über ai_task, Zuschnitt per Pillow."""

from __future__ import annotations

import asyncio
import io
import logging
import re
import time
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

from . import messages

_LOGGER = logging.getLogger(__name__)

_NUM = re.compile(r"\d+(?:[.,]\d+)?")
_DATE = re.compile(r"(?<!\d)(\d{1,2})\.(\d{1,2})\.(\d{2,4})?(?!\d)")


def to_float(text: str) -> float:
    return float(text.replace(",", "."))


def parse_date_hint(text: str, today: date | None = None) -> date | None:
    """'27.10.' oder '27.10.2026' -> date (Jahr fehlt: das jüngste Datum, das nicht in der Zukunft liegt)."""
    today = today or date.today()
    m = _DATE.search(text or "")
    if not m:
        return None
    day, month = int(m.group(1)), int(m.group(2))
    year = m.group(3)
    try:
        if year:
            y = int(year)
            return date(y + 2000 if y < 100 else y, month, day)
        d = date(today.year, month, day)
        return d if d <= today else date(today.year - 1, month, day)
    except ValueError:
        return None


def parse_time(text: str) -> tuple[int, int] | None:
    """'08:24' oder '8.24 Uhr' -> (8, 24), sonst None."""
    m = re.search(r"(?<!\d)([01]?\d|2[0-3])[:.]([0-5]\d)(?!\d)", text or "")
    return (int(m.group(1)), int(m.group(2))) if m else None


def clean_text(value, limit: int) -> str | None:
    """Text von der KI: Zeilenumbrüche zu Leerzeichen, gekürzt; leer/„null“ -> None."""
    s = re.sub(r"\s+", " ", str(value or "")).strip(" ,;")
    return s[:limit] if s and s.lower() not in ("null", "none", "n/a", "-") else None


def parse_text(text: str) -> dict[str, Any] | None:
    """'45,93 105,13' (Menge Betrag) oder '45,93 2,289 105,13' (Menge Preis Betrag), Datum optional davor."""
    clean = _DATE.sub(" ", text or "")
    nums = [to_float(n) for n in _NUM.findall(clean)]
    if len(nums) == 2:
        qty, total = nums
        price = round(total / qty, 3) if qty else None
    elif len(nums) == 3:
        qty, price, total = nums
    else:
        return None
    if qty <= 0 or total <= 0:
        return None
    return {"quantity": qty, "unit_price": price, "total": total, "date": parse_date_hint(text)}


_KM_B = re.compile(r"(?is)^\s*(\d{1,3}(?:[. ]\d{3})+|\d{4,7})\s*km\s*$")


def _alt(words) -> str:
    return "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True))


def parse_km(text: str) -> float | None:
    """'km 54210', 'Kilometerstand: 54.210', 'tacho 54 210' oder '54210 km' -> 54210.0, sonst None."""
    km_a = re.compile(r"(?is)^\s*(?:" + _alt(messages.keywords("km")) + r")(?![^\W\d_])[:=\s]*(\d{1,3}(?:[. ]\d{3})+|\d{3,7})(?:[.,]\d+)?\s*(?:km)?\s*$")
    m = km_a.match(text or "") or _KM_B.match(text or "")
    return float(re.sub(r"[. ]", "", m.group(1))) if m else None



def parse_extra(text: str) -> tuple[str, str] | None:
    """Zubehör-Nachricht erkennen: 'zubehör Öl 1 9,50', 'extra Scheibenwischer 24,90' oder Kurzwort ('adblue 5,2 12,50').
    Rückgabe (Bezeichnung, Rest mit den Zahlen) oder None; die Bezeichnung ist leer, wenn keine genannt wurde.
    Die Stichwörter stammen aus allen Sprachen (messages.py)."""
    t = (text or "").strip()
    m = re.match(r"(?is)(?:(?:" + _alt(messages.keywords("extra")) + r")(?=[:\s]|$)|\+)[:\s]*(.*)$", t)
    if m:
        mm = re.match(r"(?s)([^\d]*?)\s*(\d.*)?$", m.group(1))
        item = (mm.group(1) or "").strip(" :-,.")
        return item, (mm.group(2) or "")
    low = t.lower()
    aliases = messages.items()
    for key in sorted(aliases, key=len, reverse=True):
        if re.match(re.escape(key) + r"(?![\w-])", low):
            return aliases[key][0], t[len(key):].lstrip(" :")
    return None


def parse_extra_values(rest: str) -> dict[str, Any] | None:
    """Zahlen zu Zubehör: Menge+Betrag, Menge+Preis+Betrag oder nur der Betrag."""
    v = parse_text(rest)
    if v:
        return v
    nums = [to_float(n) for n in _NUM.findall(_DATE.sub(" ", rest or ""))]
    if len(nums) == 1 and nums[0] > 0:
        return {"quantity": None, "unit_price": None, "total": nums[0], "date": parse_date_hint(rest)}
    return None


def plausible(values: dict[str, Any]) -> bool:
    """Menge x Preis muss ungefähr den Betrag ergeben (±0,05 € plus Rundung)."""
    q, p, t = values.get("quantity"), values.get("unit_price"), values.get("total")
    if q and p and t:
        return abs(q * p - t) <= 0.05 + 0.0005 * q
    return bool(q or t)  # Menge allein (oder Betrag allein) reicht, z. B. Kundenbeleg ohne Preis


def rescale_decimals(values: dict[str, Any]) -> bool:
    """Ein Säulen-Display wird oft ohne den winzigen Dezimalpunkt gelesen (z. B. 3842 l, 1759 €/l, 6758 €). Passt Menge x Preis nicht zum Betrag, aber nach dem Verschieben
    des Kommas um 0 bis 3 Stellen je Wert eindeutig und mit möglichst wenig Verschiebung, werden die Werte korrigiert. Gibt True zurück, wenn korrigiert wurde."""
    q, p, t = values.get("quantity"), values.get("unit_price"), values.get("total")
    if not (q and p and t) or plausible(values):
        return False
    def fits(a, b, c):
        qq, pp, tt = q / 10 ** a, p / 10 ** b, t / 10 ** c
        return 1 <= qq <= 250 and 0.05 <= pp <= 60 and 1 <= tt <= 3000 and abs(qq * pp - tt) <= 0.05 + 0.0005 * qq

    for a, b, c in ((2, 3, 2), (2, 2, 2), (1, 3, 2), (1, 2, 2), (2, 3, 1), (1, 2, 1), (1, 3, 1), (2, 2, 1)):   # übliche Anzeigeformate zuerst (Menge, Preis je Einheit, Betrag)
        if fits(a, b, c):
            values["quantity"], values["unit_price"], values["total"] = round(q / 10 ** a, 2), round(p / 10 ** b, 3), round(t / 10 ** c, 2)
            return True
    best, tie = None, False
    for a in range(4):
        for b in range(4):
            for c in range(4):
                qq, pp, tt = q / 10 ** a, p / 10 ** b, t / 10 ** c
                if not (1 <= qq <= 250 and 0.05 <= pp <= 60 and 1 <= tt <= 3000):
                    continue
                if abs(qq * pp - tt) <= 0.05 + 0.0005 * qq:
                    cost = a + b + c
                    if best is None or cost < best[0]:
                        best, tie = (cost, qq, pp, tt), False
                    elif cost == best[0] and (qq, pp, tt) != best[1:]:
                        tie = True
    if best is None or tie:
        return False
    values["quantity"], values["unit_price"], values["total"] = round(best[1], 2), round(best[2], 3), round(best[3], 2)
    return True


def repair_value(values: dict[str, Any]) -> bool:
    """Passen Menge, Preis und Betrag nicht zusammen, kann genau ein Wert falsch gelesen sein (z. B. 2,6 statt 21,60). Der falsche wird aus den beiden anderen berechnet, aber nur,
    wenn genau eine der drei Möglichkeiten ein übliches Ergebnis liefert (Menge 3 bis 150, Betrag 3 bis 400, Preis je Einheit 0,05 bis 60). Sonst bleibt alles unverändert."""
    q, p, t = values.get("quantity"), values.get("unit_price"), values.get("total")
    if not (q and p and t) or plausible(values):
        return False
    ok_q = lambda x: 3 <= x <= 150   # noqa: E731
    ok_t = lambda x: 3 <= x <= 400   # noqa: E731
    cands = []
    qa = round(t / p, 2)             # Menge falsch gelesen
    if ok_q(qa) and ok_t(t) and abs(qa * p - t) <= 0.05 + 0.0005 * qa:
        cands.append(("quantity", qa))
    pb = round(t / q, 3)             # Preis falsch gelesen
    if ok_q(q) and ok_t(t) and 0.05 <= pb <= 60:
        cands.append(("unit_price", pb))
    tc = round(q * p, 2)             # Betrag falsch gelesen
    if ok_q(q) and ok_t(tc) and 0.05 <= p <= 60:
        cands.append(("total", tc))
    if len(cands) != 1:
        return False
    values[cands[0][0]] = cands[0][1]
    return True


_RATES: dict[tuple[str, str], tuple[float, str]] = {}


async def eur_rate(hass, currency: str, on: date | None) -> tuple[float, str] | None:
    """Tageskurs (EZB, über frankfurter.dev): 1 EUR = x Fremdwährung am Tag ``on`` (Wochenende/Feiertag: letzter Handelstag davor). None = nicht verfügbar."""
    key = (currency, (on or date.today()).isoformat())
    if key in _RATES:
        return _RATES[key]
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    try:
        async with asyncio.timeout(15):
            r = await async_get_clientsession(hass).get(f"https://api.frankfurter.dev/v1/{key[1]}", params={"base": "EUR", "symbols": currency})
            if r.status != 200:
                return None
            j = await r.json()
        rate = float((j.get("rates") or {}).get(currency))
        if rate > 0:
            _RATES[key] = (rate, str(j.get("date") or key[1]))
            return _RATES[key]
    except Exception as err:  # noqa: BLE001 - ohne Kurs bleibt der Beleg unumgerechnet, mit Hinweis
        _LOGGER.warning("Wechselkurs %s nicht verfügbar: %r", currency, err)
    return None


CURRENCY_BY_COUNTRY = {
    "CH": "CHF", "LI": "CHF", "GB": "GBP", "PL": "PLN", "CZ": "CZK", "HU": "HUF", "SE": "SEK", "DK": "DKK", "NO": "NOK", "RO": "RON", "IS": "ISK", "RS": "RSD",
    "BA": "BAM", "MK": "MKD", "AL": "ALL", "TR": "TRY", "UA": "UAH", "MD": "MDL", "BY": "BYN", "GE": "GEL", "US": "USD", "CA": "CAD", "MA": "MAD", "TN": "TND",
    "EG": "EGP", "ZA": "ZAR", "AE": "AED", "JP": "JPY", "AU": "AUD", "NZ": "NZD", "CN": "CNY", "IN": "INR", "BR": "BRL", "MX": "MXN", "TH": "THB",
}   # Länder mit eigener Währung; alle anderen Länder, die hier fehlen, gelten als Euro (Euroraum) und lösen keine Umrechnung aus
EURO_COUNTRIES = {"DE", "AT", "BE", "BG", "CY", "EE", "ES", "FI", "FR", "GR", "HR", "IE", "IT", "LT", "LU", "LV", "MC", "ME", "MT", "NL", "PT", "SI", "SK", "SM", "VA", "XK", "AD"}
_COUNTRY_CACHE: dict[tuple[float, float], str | None] = {}


async def country_at(hass, lat: float, lon: float) -> str | None:
    """Ländercode (ISO 3166-1 alpha-2) zu einer Position über die Rückwärtssuche von OpenStreetMap (Nominatim); nur die gerundete Position wird gesendet. None = nicht ermittelbar."""
    key = (round(lat, 1), round(lon, 1))
    if key in _COUNTRY_CACHE:
        return _COUNTRY_CACHE[key]
    import aiohttp
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    cc = None
    try:
        r = await async_get_clientsession(hass).get(
            "https://nominatim.openstreetmap.org/reverse", params={"format": "jsonv2", "lat": key[0], "lon": key[1], "zoom": 3, "addressdetails": 1},
            headers={"User-Agent": "drive-energy-doc-homeassistant"}, timeout=aiohttp.ClientTimeout(total=4))
        if r.status == 200:
            cc = str(((await r.json()).get("address") or {}).get("country_code") or "").upper() or None
    except (aiohttp.ClientError, TimeoutError, ValueError) as err:
        _LOGGER.warning("Land zur Position nicht ermittelbar: %r", err)
    if cc:
        _COUNTRY_CACHE[key] = cc
    return cc


async def assumed_currency(hass, pos: tuple[float, float] | None) -> tuple[str, str] | None:
    """Landeswährung am Aufenthaltsort, wenn der Beleg keine Währung nennt: (Währung, Land). None = unbekannt."""
    if not pos:
        return None
    cc = await country_at(hass, pos[0], pos[1])
    if not cc:
        return None
    if cc in CURRENCY_BY_COUNTRY:
        return CURRENCY_BY_COUNTRY[cc], cc
    return ("EUR", cc) if cc in EURO_COUNTRIES else None


def exif_gps(image: bytes) -> tuple[float, float] | None:
    """Aufnahmeort aus den EXIF-Daten des Fotos (Breite, Länge) oder None. Messenger entfernen ihn meist; ein als Datei gesendetes oder im Panel hochgeladenes Foto behält ihn. Läuft im Executor."""
    try:
        from PIL import Image

        gps = Image.open(io.BytesIO(image)).getexif().get_ifd(0x8825)
        if not gps or 2 not in gps or 4 not in gps:
            return None

        def deg(v, ref) -> float:
            d = float(v[0]) + float(v[1]) / 60 + float(v[2]) / 3600
            return -d if str(ref).upper() in ("S", "W") else d

        return deg(gps[2], gps.get(1)), deg(gps[4], gps.get(3))
    except Exception:  # noqa: BLE001 - kein GPS im Foto ist der Normalfall
        return None


def round_half_up(x: float, digits: int = 2) -> float:
    """Kaufmännisch runden (0,125 -> 0,13); Pythons round() rundet wegen der Binärdarstellung gelegentlich ab."""
    from decimal import ROUND_HALF_UP, Decimal

    return float(Decimal(str(x)).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP))


async def convert_to_eur(hass, out: dict[str, Any], pos: tuple[float, float] | None = None, exif: tuple[float, float] | None = None) -> None:
    """Betrag und Preis eines Belegs in Fremdwährung zum Tageskurs des Belegdatums in Euro umrechnen. Die Originalwerte stehen danach in ``out["orig"]`` (für die Notiz)."""
    cur = str(out.get("currency") or "").strip().upper().replace("€", "EUR").replace("£", "GBP")   # „eur“, „€“ usw. nicht als Fremdwährung behandeln
    assumed = None
    d = out.get("date")
    amounts = bool(out.get("total") or out.get("unit_price"))
    if not cur and amounts:
        # keine Währung erkannt: das Land verrät sie. Erst die Position des Fahrzeugs (nur bei einem Beleg von heute, sonst wäre der Ort ein anderer), dann der Aufnahmeort in den Foto-Metadaten
        got = None
        for p, today_only in ((pos, True), (exif, False)):
            if p and not got and (not today_only or d is None or abs((date.today() - d).days) <= 1):
                got = await assumed_currency(hass, p)
        if got and got[0] != "EUR":
            cur, assumed = got
        elif not got:
            out["currency"] = ""
            out["orig"] = {"currency": None, "total": out.get("total"), "unit_price": out.get("unit_price"), "rate": None, "date": None, "assumed": None, "unknown": True}   # Warnung in der Notiz, Währung von Hand wählbar
            return
    out["currency"] = cur
    if not cur or cur == "EUR" or not amounts:
        return
    orig = {"currency": cur, "total": out.get("total"), "unit_price": out.get("unit_price"), "rate": None, "date": None, "assumed": assumed}
    out["orig"] = orig
    got = await eur_rate(hass, cur, out.get("date"))
    if not got:
        return   # nicht umgerechnet: die Notiz weist darauf hin
    rate, day = got
    orig["rate"], orig["date"] = rate, day
    if out.get("total"):
        out["total"] = round_half_up(out["total"] / rate, 2)   # Betrag in Euro und Cent
    if out.get("unit_price"):
        out["unit_price"] = round_half_up(out["unit_price"] / rate, 3)   # Preis je Liter/kWh wie an der Säule auf drei Stellen


FUEL_GRADES = ("diesel", "diesel_premium", "e10", "e5", "ron95", "ron98", "lpg")   # Kraftstoffsorten eines Tankeintrags

STRUCTURE = {
    "fuel_grade": {"description": "Fuel grade if printed on the receipt or shown on the pump, one of: diesel, diesel_premium (premium / V-Power / Ultimate diesel), e10 (Super E10, E10), e5 (Super E5, E5), ron95 (95 or plain Super 95 without E5/E10), ron98 (98, Super Plus, V-Power, Ultimate petrol), lpg (autogas). Empty if not readable.", "required": False, "selector": {"text": {}}},
    "currency": {"description": "ISO 4217 code of the currency printed on the receipt, for example EUR, CHF, GBP, PLN, CZK, HUF, SEK, DKK, NOK, RON. Use the country, the language and the symbols (EUR, zl, Kc, kr, £) to decide; empty if not readable.", "required": False, "selector": {"text": {}}},
    "category": {"description": "What was bought. One of: fuel (petrol, diesel, LPG, CNG, hydrogen), charging (EV electricity), adblue (AdBlue / DEF / urea), oil (engine oil), washer (windscreen washer fluid), carwash (car wash), other (anything else for the car, e.g. wiper blades, bulbs, cleaner). Use fuel if the receipt shows fuel, even with a shop item on it.", "required": False, "selector": {"text": {}}},
    "item": {"description": "For category other only: short name of the main article as printed, empty otherwise", "required": False, "selector": {"text": {}}},
    "quantity": {"description": "Amount of fuel (litres) or energy (kWh) as a number, dot as decimal separator", "required": False, "selector": {"number": {"mode": "box", "step": "any"}}},
    "unit_price": {"description": "Price per litre or per kWh as a number (currency of the receipt, normally EUR)", "required": False, "selector": {"number": {"mode": "box", "step": "any"}}},
    "total": {"description": "Total amount paid as a number", "required": False, "selector": {"number": {"mode": "box", "step": "any"}}},
    "odometer": {"description": "Total odometer reading in km as a number (NOT the trip meter). Two cases: (1) a photo of a car instrument cluster or dashboard: read the digit display of the odometer (usually 5-6 digits, often marked total or km), no text label is needed; (2) a receipt: only if a line is explicitly labelled Kilometerstand, km-Stand, Odometer, Mileage or Compteur - never a receipt number, pump number, card number, customer number, phone number, date or time. Empty if neither case applies.", "required": False, "selector": {"number": {"mode": "box", "step": "any"}}},
    "date": {"description": "Date of the transaction as DD.MM.YYYY, empty if not readable", "required": False, "selector": {"text": {}}},
    "time": {"description": "Time of the transaction as HH:MM (24 hours), empty if not readable", "required": False, "selector": {"text": {}}},
    "station": {"description": "Name of the filling station or merchant as printed at the top of the receipt, empty if not readable", "required": False, "selector": {"text": {}}},
    "address": {"description": "Address of the station on one line (street and number, postal code and city) as printed, empty if not readable", "required": False, "selector": {"text": {}}},
    "crop": {"description": "Bounding box of the receipt or display in the image: four numbers from 0 to 1000 separated by commas in the order ymin,xmin,ymax,xmax (fractions of the image height and width). ALWAYS provide it, even if the receipt fills almost the whole image; only the paper or the display, without table or background.", "required": False, "selector": {"text": {}}},
}

# Anweisung auf Englisch: funktioniert mit allen KI-Anbietern zuverlässiger, die Belege selbst dürfen in jeder Sprache sein
INSTRUCTIONS = (
    "The image shows ONE of these: (A) a fuel or EV-charging receipt or a pump/charger display, or (B) a photo of a car instrument cluster or dashboard. "
    "The text may be in any language (German, French, Dutch, Polish, Italian, Spanish, and so on). "
    "CASE B, instrument cluster: return ONLY the total odometer reading (odometer): the small digital or mechanical digit display, usually 5 or 6 digits, often marked total or km, "
    "NOT the trip meter and NOT the speed or fuel gauge. No text label is needed; the display may be dim, tilted, low-contrast, blurred or partly reflecting light, so read it carefully. Leave all other fields empty. "
    "CASE A may also be a receipt for AdBlue, oil, washer fluid, a car wash or other car accessories: set the category accordingly; for those, quantity is the amount in litres or pieces (empty for a car wash). "
    "CASE A, receipt or pump display: extract the amount of fuel or energy (litres or kWh; on receipts often labelled Volumen, Menge, Liter, Volume, Quantité, Quantity); "
    "the price per unit; the total amount paid (Summe, Betrag, Total, Montant); the date and time; and the name and address of the filling station or merchant (usually at the top of the receipt). "
    "On a receipt the odometer is returned ONLY if a line is explicitly labelled as such (Kilometerstand, km-Stand, Odometer, Mileage, Compteur); receipt numbers, pump numbers, card numbers, "
    "customer numbers and phone numbers are NOT the odometer, and most receipts have no odometer line, so leave it empty then. "
    "A pump or charger display (seven-segment LCD) usually shows three lines: the amount to pay, the volume (litres) or energy (kWh) and the price per litre or kWh. Read all three; "
    "ignore dim, unlit segments, and look closely for the small decimal point: amounts and volumes normally have two decimals, the price per litre three decimals (for example 67.58, 38.42 and 1.759). "
    "Numbers: dot as decimal separator, no thousands separators, no currency symbols. "
    "Only return values you can read with certainty, otherwise leave the field empty. Never guess and never calculate missing values. "
    "Always return the crop box that contains only the receipt or the display."
)


async def ai_read(hass, entity_id: str, image: bytes, media_dir: Path, pos: tuple[float, float] | None = None, exif: tuple[float, float] | None = None) -> dict[str, Any] | None:
    """Beleg per ai_task lesen. None = nicht verfügbar oder nichts Lesbares."""
    if not entity_id or not hass.services.has_service("ai_task", "generate_data"):
        return None
    folder = media_dir / "drive_energy_doc_tmp"
    name = f"{uuid.uuid4().hex}.jpg"

    def _write() -> None:
        folder.mkdir(parents=True, exist_ok=True)
        data = image
        try:   # lange Seite höchstens 1568 px: genug für Belegtext, weniger Daten und Tokens (schneller)
            from PIL import Image

            img = Image.open(io.BytesIO(image))
            if max(img.size) > 1568:
                img.thumbnail((1568, 1568))
                buf = io.BytesIO()
                img.convert("RGB").save(buf, "JPEG", quality=85)
                data = buf.getvalue()
        except Exception:  # noqa: BLE001 - dann das Original senden
            data = image
        (folder / name).write_bytes(data)

    await hass.async_add_executor_job(_write)
    t_ai = time.monotonic()
    resp = None
    try:
        for attempt, wait in enumerate((4, 10, None)):   # Die KI-Anbieter melden Überlastung mit 503 (Gemini) bzw. 529 (Claude): ein paar Mal mit Pause wiederholen
            try:
                resp = await asyncio.wait_for(
                    hass.services.async_call(
                        "ai_task",
                        "generate_data",
                        {
                            "entity_id": entity_id,
                            "task_name": "fuel_receipt",
                            "instructions": INSTRUCTIONS,
                            "structure": STRUCTURE,
                            "attachments": [{"media_content_id": f"media-source://media_source/local/drive_energy_doc_tmp/{name}", "media_content_type": "image/jpeg"}],
                        },
                        blocking=True,
                        return_response=True,
                    ),
                    timeout=75,   # Gemini braucht bei Fotos meist 5 bis 30 s; was länger dauert, hängt in der Regel
                )
                break
            except Exception as err:  # noqa: BLE001 - KI-Fehler dürfen nie den Ablauf stoppen
                busy = isinstance(err, asyncio.TimeoutError) or any(s in repr(err) for s in ("503", "UNAVAILABLE", "429", "high demand", "overloaded", "RESOURCE_EXHAUSTED", "entity_not_found", "529", "overloaded_error", "rate_limit"))   # entity_not_found: die KI ist kurz nach dem HA-Start noch nicht geladen
                _LOGGER.warning("Beleg-KI fehlgeschlagen (Versuch %d): %r", attempt + 1, err)
                if not busy:
                    return None
                if wait is None:
                    return {"busy": True}   # KI überlastet: kein „nichts gelesen“, der Aufrufer sagt das dem Nutzer
                await asyncio.sleep(wait)
    finally:
        await hass.async_add_executor_job(lambda: (folder / name).unlink(missing_ok=True))
    ai_secs = round(time.monotonic() - t_ai, 1)
    _LOGGER.info("Beleg-KI: Antwort nach %.1f s (%s, Bild %d KB)", ai_secs, entity_id, len(image) // 1024)
    data = (resp or {}).get("data") or {}

    def num(key: str) -> float | None:
        try:
            v = float(str(data.get(key)).replace(",", "."))
            return v if v > 0 else None
        except (TypeError, ValueError):
            return None

    out = {"quantity": num("quantity"), "unit_price": num("unit_price"), "total": num("total"), "odometer": num("odometer"), "date": parse_date_hint(str(data.get("date") or "")), "time": parse_time(str(data.get("time") or "")), "currency": (re.sub(r"[^A-Z]", "", str(data.get("currency") or "").upper())[:3] or None), "category": (lambda c: c if c in ("fuel", "charging", "adblue", "oil", "washer", "carwash", "other") else None)(re.sub(r"[^a-z]", "", str(data.get("category") or "").lower())), "ai_secs": ai_secs, "fuel_grade": (lambda c: c if c in FUEL_GRADES else None)(re.sub(r"[^a-z0-9_]", "", str(data.get("fuel_grade") or "").lower())), "item": clean_text(data.get("item"), 60), "station": clean_text(data.get("station"), 60), "address": clean_text(data.get("address"), 120), "crop": None}
    box = [int(float(x)) for x in re.findall(r"\d+(?:\.\d+)?", str(data.get("crop") or ""))]
    if len(box) == 4 and box[2] > box[0] and box[3] > box[1] and all(0 <= b <= 1000 for b in box):
        out["crop"] = box
    if rescale_decimals(out):
        _LOGGER.info("Beleg-KI: Dezimalpunkt am Säulen-Display korrigiert (Menge %s, Preis %s, Betrag %s)", out["quantity"], out["unit_price"], out["total"])
    elif repair_value(out):
        _LOGGER.info("Beleg-KI: einen falsch gelesenen Wert aus den beiden anderen berechnet (Menge %s, Preis %s, Betrag %s)", out["quantity"], out["unit_price"], out["total"])
    if not (out["quantity"] or out["total"] or out["odometer"]):
        _LOGGER.warning("Beleg-KI: keine Zahlen im Ergebnis gelesen (Kategorie %s)", out.get("category"))
        return None   # ein Tacho-Foto hat nur den Kilometerstand
    if not plausible(out) and not out["odometer"]:
        _LOGGER.warning("Beleg-KI: Werte passen nicht zusammen: Menge %s, Preis %s, Betrag %s", out["quantity"], out["unit_price"], out["total"])
    await convert_to_eur(hass, out, pos, exif)   # Fremdwährung: zum Tageskurs des Belegdatums in Euro
    return out


def auto_box(img) -> list[int] | None:
    """Beleg im Bild finden: helle, kaum gesättigte Fläche (Papier) auf dunklerem Untergrund. Box 0-1000 (ymin,xmin,ymax,xmax) oder None."""
    from PIL import Image, ImageChops, ImageFilter

    small = img.copy()
    small.thumbnail((400, 400))
    h_, s_, v_ = small.convert("HSV").split()
    mask = ImageChops.multiply(s_.point(lambda x: 255 if x < 80 else 0), v_.point(lambda x: 255 if x > 145 else 0))
    mask = mask.filter(ImageFilter.MedianFilter(5))
    w, h = small.size
    cols = list(mask.resize((w, 1), Image.BOX).getdata())
    rows = list(mask.resize((1, h), Image.BOX).getdata())
    if not cols or max(cols) < 30 or max(rows) < 30:
        return None

    def span(vals):
        limit = 0.35 * max(vals)
        idx = [i for i, v in enumerate(vals) if v >= limit]
        return idx[0], idx[-1] + 1

    x0, x1 = span(cols)
    y0, y1 = span(rows)
    area = (x1 - x0) * (y1 - y0) / (w * h)
    if area > 0.92 or area < 0.12:  # ganzes Bild oder winziger Fleck: lieber nicht zuschneiden
        return None
    if (y1 - y0) < 1.6 * (x1 - x0):  # Kassenbons sind hoch und schmal; alles andere (Zapfsäule, Querformat) bleibt unbeschnitten
        return None
    return [int(y0 / h * 1000), int(x0 / w * 1000), int(y1 / h * 1000), int(x1 / w * 1000)]


def crop_and_save(image: bytes, box: list[int] | None, folder: Path, name: str, keep_original: Path | None = None) -> str:
    """Zuschneiden (Box 0-1000: ymin,xmin,ymax,xmax), als JPEG speichern, Original optional sichern. Läuft im Executor."""
    folder.mkdir(parents=True, exist_ok=True)
    if keep_original:
        keep_original.mkdir(parents=True, exist_ok=True)
        (keep_original / name).write_bytes(recompress(image, 1800, 82))   # Original: etwas kleiner, aber immer noch voll lesbar
    data = image
    try:
        from PIL import Image, ImageOps  # Pillow liegt Home Assistant bei

        img = ImageOps.exif_transpose(Image.open(io.BytesIO(image))).convert("RGB")
        if not box:
            box = auto_box(img)
        if box:
            w, h = img.size
            pad = 15  # etwas Rand, die KI-Box sitzt oft knapp
            y0, x0, y1, x1 = max(0, box[0] - pad), max(0, box[1] - pad), min(1000, box[2] + pad), min(1000, box[3] + pad)
            img = img.crop((int(x0 * w / 1000), int(y0 * h / 1000), int(x1 * w / 1000), int(y1 * h / 1000)))
        img.thumbnail((1400, 1400))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=80, optimize=True, progressive=True)
        data = buf.getvalue()
    except Exception as err:  # noqa: BLE001 - dann bleibt das Original
        _LOGGER.warning("Zuschnitt nicht möglich, Original bleibt: %s", err)
    (folder / name).write_bytes(data)
    return name


def exif_time(image: bytes):
    """Aufnahmezeit aus den EXIF-Daten des Fotos (naive Ortszeit der Kamera) oder None. Läuft im Executor."""
    try:
        from datetime import datetime

        from PIL import Image

        ex = Image.open(io.BytesIO(image)).getexif()
        raw = ex.get_ifd(0x8769).get(36867) or ex.get_ifd(0x8769).get(36868) or ex.get(306)
        return datetime.strptime(str(raw).strip()[:19], "%Y:%m:%d %H:%M:%S") if raw else None
    except Exception:  # noqa: BLE001 - kein EXIF ist der Normalfall (Messenger entfernen es)
        return None


def normalize(image: bytes, max_side: int = 2000) -> bytes:
    """Handyfoto: EXIF-Drehung anwenden, auf max_side verkleinern, als JPEG. Bei Fehler Original. Läuft im Executor."""
    try:
        from PIL import Image, ImageOps

        img = ImageOps.exif_transpose(Image.open(io.BytesIO(image))).convert("RGB")
        img.thumbnail((max_side, max_side))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=88)
        return buf.getvalue()
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("Foto nicht normalisiert: %s", err)
        return image


def save_vehicle_image(data: bytes, folder: Path, max_side: int = 1000) -> str:
    """Hochgeladenes Fahrzeugbild verkleinern und speichern (PNG mit Transparenz bleibt PNG). Läuft im Executor."""
    from PIL import Image, ImageOps

    img = ImageOps.exif_transpose(Image.open(io.BytesIO(data)))
    img.thumbnail((max_side, max_side))
    alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}.{'png' if alpha else 'jpg'}"
    if alpha:
        img.convert("RGBA").save(folder / name, "PNG", optimize=True)
    else:
        img.convert("RGB").save(folder / name, "JPEG", quality=88)
    return name


_FOLD = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss", "æ": "ae", "ø": "o", "å": "a", "ł": "l", "Ł": "L", "đ": "d", "ð": "d", "þ": "th"})
_LABEL = {"fuel": "Tanken", "charging": "Laden", "adblue": "AdBlue", "oil": "Oel", "washer": "Scheibenreiniger", "carwash": "Autowaesche"}


def slug(text: Any, n: int = 32) -> str:
    """Text als Dateinamenteil: nur A-Z a-z 0-9, Wörter mit Bindestrich (Umlaute werden aufgelöst)."""
    import unicodedata

    s = unicodedata.normalize("NFKD", str(text or "").translate(_FOLD))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-")[:n].strip("-")


def new_photo_name(values: dict | None = None, ts: float | None = None, label: str | None = None, folder: Path | None = None) -> str:
    """Sprechender Dateiname: ``2026-10-15_1240_Oel_Cerpaci-stanice-Zlaty-Lan.jpg`` (Datum und Uhrzeit vom Beleg, sonst ``ts``, sonst jetzt;
    dann Art und Händler). Gibt es den Namen im ``folder`` schon, wird ``_2``, ``_3`` … angehängt."""
    v = values or {}
    d, hm = v.get("date"), v.get("time")
    if d:
        when = datetime(d.year, d.month, d.day, *(hm or (12, 0)))
    else:
        when = datetime.fromtimestamp(ts or time.time())
    if not label:
        cat = v.get("category")
        label = _LABEL.get(cat) or (slug(v.get("item"), 24) if cat == "other" else "") or ("Beleg" if (v.get("quantity") or v.get("total")) else ("Tacho" if v.get("odometer") else "Foto"))
    parts = [f"{when:%Y-%m-%d_%H%M}", slug(label, 24) or "Foto"]
    st = slug(v.get("station"), 32)
    if st:
        parts.append(st)
    base = "_".join(parts)
    name, i = f"{base}.jpg", 2
    while folder is not None and (folder / name).exists():
        name, i = f"{base}_{i}.jpg", i + 1
    return name


def recompress(data: bytes, max_side: int, quality: int) -> bytes:
    """JPEG verkleinern und stärker komprimieren (progressiv, optimiert). Gibt das Original zurück, wenn das Ergebnis nicht kleiner ist. Läuft im Executor."""
    try:
        from PIL import Image, ImageOps

        img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
        img.thumbnail((max_side, max_side))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
        return buf.getvalue() if len(buf.getvalue()) < len(data) else data
    except Exception:  # noqa: BLE001
        return data


def fmt_dt(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M")
