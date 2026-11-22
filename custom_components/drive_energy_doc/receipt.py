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


STRUCTURE = {
    "quantity": {"description": "Amount of fuel (litres) or energy (kWh) as a number, dot as decimal separator", "required": False, "selector": {"number": {"mode": "box", "step": "any"}}},
    "unit_price": {"description": "Price per litre or per kWh as a number (currency of the receipt, normally EUR)", "required": False, "selector": {"number": {"mode": "box", "step": "any"}}},
    "total": {"description": "Total amount paid as a number", "required": False, "selector": {"number": {"mode": "box", "step": "any"}}},
    "odometer": {"description": "Odometer reading in km as a number (total distance, not the trip meter), only if shown", "required": False, "selector": {"number": {"mode": "box", "step": "any"}}},
    "date": {"description": "Date of the transaction as DD.MM.YYYY, empty if not readable", "required": False, "selector": {"text": {}}},
    "time": {"description": "Time of the transaction as HH:MM (24 hours), empty if not readable", "required": False, "selector": {"text": {}}},
    "station": {"description": "Name of the filling station or merchant as printed at the top of the receipt, empty if not readable", "required": False, "selector": {"text": {}}},
    "address": {"description": "Address of the station on one line (street and number, postal code and city) as printed, empty if not readable", "required": False, "selector": {"text": {}}},
    "crop": {"description": "Bounding box of the receipt or display in the image: four numbers from 0 to 1000 separated by commas in the order ymin,xmin,ymax,xmax (fractions of the image height and width). ALWAYS provide it, even if the receipt fills almost the whole image; only the paper or the display, without table or background.", "required": False, "selector": {"text": {}}},
}

# Anweisung auf Englisch: funktioniert mit allen KI-Anbietern zuverlässiger, die Belege selbst dürfen in jeder Sprache sein
INSTRUCTIONS = (
    "The image shows a fuel or EV-charging receipt, a pump or charger display, or a car instrument cluster. "
    "The text may be in any language (German, French, Dutch, Polish, Italian, Spanish, and so on). "
    "Extract: the amount of fuel or energy (litres or kWh; on receipts often labelled Volumen, Menge, Liter, Volume, Quantité, Quantity); "
    "the price per unit; the total amount paid (Summe, Betrag, Total, Montant); the odometer reading if it is printed on the receipt (Kilometerstand, km); "
    "the date and time; and the name and address of the filling station or merchant (usually at the top of the receipt). "
    "If the image shows an instrument cluster, return the total odometer reading (odometer), NOT the trip meter, and leave the other fields empty. "
    "Numbers: dot as decimal separator, no thousands separators, no currency symbols. "
    "Only return values you can read with certainty, otherwise leave the field empty. Never guess and never calculate missing values. "
    "Always return the crop box that contains only the receipt or the display."
)


async def ai_read(hass, entity_id: str, image: bytes, media_dir: Path) -> dict[str, Any] | None:
    """Beleg per ai_task lesen. None = nicht verfügbar oder nichts Lesbares."""
    if not entity_id or not hass.services.has_service("ai_task", "generate_data"):
        return None
    folder = media_dir / "drive_energy_doc_tmp"
    name = f"{uuid.uuid4().hex}.jpg"

    def _write() -> None:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / name).write_bytes(image)

    await hass.async_add_executor_job(_write)
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
            timeout=120,
        )
    except Exception as err:  # noqa: BLE001 - KI-Fehler dürfen nie den Ablauf stoppen
        _LOGGER.warning("Beleg-KI fehlgeschlagen: %r", err)
        return None
    finally:
        await hass.async_add_executor_job(lambda: (folder / name).unlink(missing_ok=True))
    data = (resp or {}).get("data") or {}

    def num(key: str) -> float | None:
        try:
            v = float(str(data.get(key)).replace(",", "."))
            return v if v > 0 else None
        except (TypeError, ValueError):
            return None

    out = {"quantity": num("quantity"), "unit_price": num("unit_price"), "total": num("total"), "odometer": num("odometer"), "date": parse_date_hint(str(data.get("date") or "")), "time": parse_time(str(data.get("time") or "")), "station": clean_text(data.get("station"), 60), "address": clean_text(data.get("address"), 120), "crop": None}
    box = [int(float(x)) for x in re.findall(r"\d+(?:\.\d+)?", str(data.get("crop") or ""))]
    if len(box) == 4 and box[2] > box[0] and box[3] > box[1] and all(0 <= b <= 1000 for b in box):
        out["crop"] = box
    return out if (out["quantity"] or out["total"] or out["odometer"]) else None   # ein Tacho-Foto hat nur den Kilometerstand


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
        (keep_original / name).write_bytes(image)
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
        img.thumbnail((1600, 1600))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=85)
        data = buf.getvalue()
    except Exception as err:  # noqa: BLE001 - dann bleibt das Original
        _LOGGER.warning("Zuschnitt nicht möglich, Original bleibt: %s", err)
    (folder / name).write_bytes(data)
    return name


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


def new_photo_name() -> str:
    return f"{int(time.time())}_{uuid.uuid4().hex[:10]}.jpg"


def fmt_dt(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M")
