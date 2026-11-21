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


_KM_A = re.compile(r"(?is)^\s*(?:km|kilometer(?:stand)?|tacho|odometer)\b[:=\s]*(\d{1,3}(?:[. ]\d{3})+|\d{3,7})(?:[.,]\d+)?\s*(?:km)?\s*$")
_KM_B = re.compile(r"(?is)^\s*(\d{1,3}(?:[. ]\d{3})+|\d{4,7})\s*km\s*$")


def parse_km(text: str) -> float | None:
    """'km 54210', 'Kilometerstand: 54.210', 'tacho 54 210' oder '54210 km' -> 54210.0, sonst None."""
    m = _KM_A.match(text or "") or _KM_B.match(text or "")
    return float(re.sub(r"[. ]", "", m.group(1))) if m else None


ALIASES = {
    "adblue": "AdBlue", "ad blue": "AdBlue", "ad-blue": "AdBlue", "motoröl": "Motoröl", "motoroel": "Motoröl", "öl": "Öl", "oel": "Öl",
    "scheibenwischer": "Scheibenwischer", "wischer": "Scheibenwischer", "scheibenwasser": "Scheibenwasser", "frostschutz": "Frostschutz",
}


def parse_extra(text: str) -> tuple[str, str] | None:
    """Zubehör-Nachricht erkennen: 'zubehör Öl 1 9,50', 'extra Scheibenwischer 24,90' oder Kurzwort ('adblue 5,2 12,50').
    Rückgabe (Bezeichnung, Rest mit den Zahlen) oder None."""
    t = (text or "").strip()
    m = re.match(r"(?is)(?:(?:zubeh(?:ö|oe)r|zub|extra|z|e|x)(?=[:\s]|$)|\+)[:\s]*(.*)$", t)
    if m:
        mm = re.match(r"(?s)([^\d]*?)\s*(\d.*)?$", m.group(1))
        item = (mm.group(1) or "").strip(" :-,.")
        return (item or "Zubehör"), (mm.group(2) or "")
    low = t.lower()
    for key in sorted(ALIASES, key=len, reverse=True):
        if re.match(re.escape(key) + r"(?![\w-])", low):
            return ALIASES[key], t[len(key):].lstrip(" :")
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
    "quantity": {"description": "Getankte Menge (Liter bzw. kWh) als Zahl, Punkt als Dezimaltrenner", "required": False, "selector": {"number": {"mode": "box", "step": "any"}}},
    "unit_price": {"description": "Preis pro Liter bzw. kWh in EUR als Zahl", "required": False, "selector": {"number": {"mode": "box", "step": "any"}}},
    "total": {"description": "Gesamtbetrag in EUR als Zahl", "required": False, "selector": {"number": {"mode": "box", "step": "any"}}},
    "odometer": {"description": "Kilometerstand des Fahrzeugs als Zahl, falls auf dem Beleg", "required": False, "selector": {"number": {"mode": "box", "step": "any"}}},
    "date": {"description": "Datum des Tankvorgangs als DD.MM.YYYY, leer wenn nicht lesbar", "required": False, "selector": {"text": {}}},
    "crop": {"description": "Begrenzungsrahmen des Belegs bzw. der Anzeige im Bild: vier Zahlen von 0 bis 1000 durch Komma in der Reihenfolge ymin,xmin,ymax,xmax (Anteile von Bildhöhe und Bildbreite). IMMER angeben, auch wenn der Beleg fast das ganze Bild füllt; nur das Papier bzw. die Anzeige, ohne Tisch oder Hintergrund.", "required": False, "selector": {"text": {}}},
}

INSTRUCTIONS = (
    "Das Bild zeigt einen Tankbeleg oder eine Zapfsäulen-/Ladesäulenanzeige. "
    "Lies die getankte Menge, den Preis pro Einheit, den Gesamtbetrag, den Kilometerstand und, falls sichtbar, das Datum. "
    "Zeigt das Bild ein Kombiinstrument (Tacho), lies den Gesamtkilometerstand (odometer), nicht den Tageskilometerzähler. Gib nur Werte zurück, die du sicher lesen kannst; sonst lass das Feld leer. Rate nicht. Gib aber immer den Bildausschnitt (crop) an, der nur den Beleg zeigt."
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
                    "task_name": "tankbeleg",
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
        _LOGGER.warning("Beleg-KI fehlgeschlagen: %s", err)
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

    out = {"quantity": num("quantity"), "unit_price": num("unit_price"), "total": num("total"), "odometer": num("odometer"), "date": parse_date_hint(str(data.get("date") or "")), "crop": None}
    box = [int(float(x)) for x in re.findall(r"\d+(?:\.\d+)?", str(data.get("crop") or ""))]
    if len(box) == 4 and box[2] > box[0] and box[3] > box[1] and all(0 <= b <= 1000 for b in box):
        out["crop"] = box
    return out if (out["quantity"] or out["total"]) else None


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
