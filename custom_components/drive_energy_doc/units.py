"""Einheiten der Installation: intern rechnet und speichert Drive Energy Doc immer metrisch (km, Liter, kWh, l/100 km).

Nur Ein- und Ausgabe richten sich nach dem Einheitensystem von Home Assistant (Einstellungen → System → Allgemein):
- metrisch: km, l, l/100 km, kWh/100 km
- US (imperial, außer GB): Meilen, US-Gallonen, mpg (US), kWh/100 mi
- GB (imperial und Land GB): Meilen, Liter (an der Zapfsäule), mpg (britische Gallone), kWh/100 mi
"""

from __future__ import annotations

KM_PER_MI = 1.609344
L_PER_GAL_US = 3.785411784
L_PER_GAL_UK = 4.54609


def system(hass) -> dict:
    """Einheiten für Anzeige und Eingabe. ``dist`` km|mi, ``vol`` l|gal, ``cons`` l/100km|mpg, ``mpg_l`` Liter je Gallone für mpg."""
    cfg = getattr(hass, "config", None)
    u = getattr(cfg, "units", None)
    length = str(getattr(u, "length_unit", "km") or "km")
    imperial = length == "mi"
    if not imperial:
        return {"sys": "metric", "dist": "km", "vol": "l", "cons": "l/100km", "mpg_l": None}
    if str(getattr(cfg, "country", "") or "").upper() == "GB":
        return {"sys": "uk", "dist": "mi", "vol": "l", "cons": "mpg", "mpg_l": L_PER_GAL_UK}
    return {"sys": "us", "dist": "mi", "vol": "gal", "cons": "mpg", "mpg_l": L_PER_GAL_US}


# ---------------------------------------------------------------- Eingabe -> metrisch
def to_km(value: float | None, unit: str | None) -> float | None:
    """Strecke/Kilometerstand in km (``unit`` mi oder km)."""
    if value is None:
        return None
    return value * KM_PER_MI if str(unit or "").lower() in ("mi", "mile", "miles", "meilen") else value


def to_l(value: float | None, unit: str | None, sys: dict | None = None) -> float | None:
    """Menge in Liter (``unit`` gal/l); eine Gallone ist die US-Gallone, in GB die britische."""
    if value is None:
        return None
    if str(unit or "").lower() in ("gal", "gallon", "gallons", "g"):
        return value * (L_PER_GAL_UK if sys and sys.get("sys") == "uk" else L_PER_GAL_US)
    return value


def price_to_per_l(value: float | None, unit: str | None, sys: dict | None = None) -> float | None:
    """Preis je Gallone -> Preis je Liter."""
    if value is None:
        return None
    if str(unit or "").lower() in ("gal", "gallon", "gallons", "g"):
        return value / (L_PER_GAL_UK if sys and sys.get("sys") == "uk" else L_PER_GAL_US)
    return value


# ---------------------------------------------------------------- metrisch -> Anzeige
def dist(sys: dict, km: float | None) -> float | None:
    return None if km is None else (km / KM_PER_MI if sys["dist"] == "mi" else km)


def vol(sys: dict, liters: float | None) -> float | None:
    return None if liters is None else (liters / L_PER_GAL_US if sys["vol"] == "gal" else liters)


def price(sys: dict, per_l: float | None) -> float | None:
    return None if per_l is None else (per_l * L_PER_GAL_US if sys["vol"] == "gal" else per_l)


def cons(sys: dict, value: float | None, electric: bool) -> float | None:
    """Verbrauch: l/100 km -> mpg bzw. kWh/100 km -> kWh/100 mi."""
    if value is None:
        return None
    if sys["dist"] != "mi":
        return value
    if electric:
        return value * KM_PER_MI
    return (100 * sys["mpg_l"] / KM_PER_MI) / value if value > 0 else None


def cons_unit(sys: dict, electric: bool, fuel_unit: str = "l") -> str:
    if electric:
        return "kWh/100 mi" if sys["dist"] == "mi" else "kWh/100 km"
    return "mpg" if sys["dist"] == "mi" else f"{fuel_unit}/100 km"


def vol_unit(sys: dict, electric: bool) -> str:
    return "kWh" if electric else sys["vol"]
