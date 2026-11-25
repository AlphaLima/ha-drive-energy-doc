"""Schätzung, Korrekturfaktor und Ladeart (AC/DC) als reine Funktionen, ohne Home-Assistant-Abhängigkeit, daher testbar.

* Die Schätzung einer Ladung oder Betankung ist Zuwachs (Prozent) mal Kapazität. Der Beleg ersetzt die Menge im Eintrag,
  die Schätzung bleibt als ``est_quantity`` stehen. Aus beiden folgt ein Korrekturfaktor (Beleg geteilt durch Schätzung), der
  Ladeverluste und Fehler der Kapazitätsangabe enthält. Er wird für Einträge ohne Beleg angewendet.
* Die Ladeart wird nur vermutet und mit der Quelle gespeichert: Sensor, Beleg, Leistung (Spitze) oder mittlere Leistung.
  Langsames DC lässt sich nicht von AC trennen, darum gibt es auch „unbekannt“.
"""

from __future__ import annotations

from statistics import median
from typing import Any

MIN_SAMPLES = 3            # so viele Einträge mit Beleg und Schätzung braucht ein Korrekturfaktor
FACTOR_RANGE = (0.5, 1.6)  # Faktoren außerhalb gelten als Messfehler und zählen nicht
DEFAULT_AC_MAX_KW = 11.0
DC_MARGIN = 1.1            # Leistung über Grenze mal Spielraum gilt als DC
MIN_AVG_MINUTES = 5.0      # kürzere Ladungen sind für eine mittlere Leistung zu ungenau
MIN_AVG_PERCENT = 5.0

DC_PARTS = ("ccs", "chademo", "schnell", "fast", "rapid", "gleichstrom", "supercharger", "hpc")   # Teile von Wörtern („Schnellladen“)
AC_PARTS = ("type2", "type 2", "typ2", "typ 2", "mennekes", "wechselstrom", "wallbox", "slow")


def parse_type(text: Any) -> str | None:
    """Ladeart aus dem Text eines Sensors oder der KI: ``dc``, ``ac`` oder None bei keiner oder widersprüchlicher Angabe (etwa „AC/DC“)."""
    t = str(text or "").strip().lower()
    if not t or t in ("unknown", "unavailable", "none", "null", "-"):
        return None
    words = "".join(c if c.isalnum() else " " for c in t).split()
    dc = "dc" in words or any(p in t for p in DC_PARTS)
    ac = "ac" in words or any(p in t for p in AC_PARTS)
    if dc and not ac:
        return "dc"
    if ac and not dc:
        return "ac"
    return None


def est_quantity(e: dict[str, Any], capacity: float) -> float | None:
    """Schätzung der Menge: gespeichert (``est_quantity``) oder aus Zuwachs und Kapazität neu gerechnet."""
    if e.get("est_quantity"):
        return float(e["est_quantity"])
    if e.get("level_from") is not None and e.get("level_to") is not None and capacity:
        pct = float(e["level_to"]) - float(e["level_from"])
        return round(pct / 100 * capacity, 2) if pct > 0 else None
    return None


def samples(entries: list[dict[str, Any]], kind: str, capacity: float, ctype: str | None = None) -> list[float]:
    """Faktoren Beleg/Schätzung der Einträge dieser Energieart (``electric`` oder ``fuel``), optional nur einer Ladeart."""
    out = []
    for e in entries:
        if e.get("kind") == "extra" or ("electric" if e.get("energy") == "electric" else "fuel") != kind:
            continue
        if e.get("quantity_source") not in ("beleg", "wallbox") or not e.get("quantity"):
            continue
        if ctype is not None and e.get("charge_type") != ctype:
            continue
        est = est_quantity(e, capacity)
        if not est:
            continue
        f = float(e["quantity"]) / est
        if FACTOR_RANGE[0] <= f <= FACTOR_RANGE[1]:
            out.append(f)
    return out


def factor(entries: list[dict[str, Any]], kind: str, capacity: float, ctype: str | None = None) -> tuple[float | None, int, str]:
    """Korrekturfaktor, Anzahl der Einträge und Gruppe (``ac``/``dc``/``all``). Bei bekannter Ladeart zuerst nur diese Art, sonst alle zusammen; unter drei Einträgen kein Faktor."""
    if ctype in ("ac", "dc"):
        s = samples(entries, kind, capacity, ctype)
        if len(s) >= MIN_SAMPLES:
            return round(median(s), 3), len(s), ctype
    s = samples(entries, kind, capacity)
    if len(s) >= MIN_SAMPLES:
        return round(median(s), 3), len(s), "all"
    return None, len(s), "all"


def classify(sensor_type: str | None, peak_w: float | None, avg_kw: float | None, ac_max_kw: float | None) -> tuple[str | None, str | None, float | None]:
    """Ladeart (``ac``/``dc``/None), Quelle (``sensor``/``leistung``/``mittel``) und die gemessene Leistung in kW.

    Reihenfolge: Sensor der Fahrzeug-Integration, Spitzenleistung eines Leistungssensors, mittlere Leistung aus Zuwachs und Dauer.
    Die mittlere Leistung beweist nur DC (über der Grenze), niemals AC: eine lange oder unterbrochene Ladung wirkt langsam."""
    limit = (ac_max_kw or DEFAULT_AC_MAX_KW) * DC_MARGIN
    if sensor_type in ("ac", "dc"):
        return sensor_type, "sensor", (round(peak_w / 1000, 1) if peak_w else None)
    if peak_w:
        kw = peak_w / 1000
        return ("dc" if kw > limit else "ac"), "leistung", round(kw, 1)
    if avg_kw and avg_kw > limit:
        return "dc", "mittel", round(avg_kw, 1)
    return None, None, (round(avg_kw, 1) if avg_kw else None)


def avg_power_kw(qty_kwh: float | None, start_ts: float | None, end_ts: float | None, pct: float | None) -> float | None:
    """Mittlere Leistung in kW aus Menge und Dauer; zu kurze oder kleine Ladungen liefern None."""
    if not qty_kwh or start_ts is None or end_ts is None or pct is None or pct < MIN_AVG_PERCENT:
        return None
    minutes = (end_ts - start_ts) / 60
    if minutes < MIN_AVG_MINUTES:
        return None
    return qty_kwh / (minutes / 60)
