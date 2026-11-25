"""Heim-Wallbox: Zählerverlauf und Zuordnung der gelieferten Energie zu einer Ladung des Autos, als reine Funktionen ohne Home-Assistant-Abhängigkeit.

Die Wallbox liefert den Zählerstand (kWh, wächst nur beim Laden) und optional die Leistung. Weil das Auto seinen Füllstand oft verspätet meldet, wird der
Verlauf laufend mitgeschrieben; beim Abschluss einer Ladung wird die Differenz zwischen Beginn und Ende gebildet. Passt sie nicht zur Schätzung aus dem Füllstand,
hat das Auto nicht an dieser Wallbox geladen und die Menge wird nicht übernommen.
"""

from __future__ import annotations

from collections import deque
from typing import Any

LEAD_SECONDS = 900.0        # ohne Leistungssensor: so weit vor dem ersten Füllstandsanstieg beginnt die Differenz
IDLE_WATT = 50.0            # darunter gilt die Wallbox als nicht ladend
RATIO_RANGE = (0.85, 1.7)   # Wallbox-kWh geteilt durch Akku-kWh: kleiner geht kaum (Messfehler der Kapazität), größer sind Ladeverluste
MAX_SAMPLES = 600


def to_kwh(value: float, unit: str | None) -> float:
    """Zählerstand in kWh (manche Zähler melden Wh)."""
    return value / 1000 if str(unit or "").strip().lower() == "wh" else value


def to_watt(value: float, unit: str | None) -> float:
    return value * 1000 if str(unit or "").strip().lower() == "kw" else value


class Log:
    """Verlauf (Zeit, kWh, Watt) einer Wallbox, nur im Speicher."""

    def __init__(self) -> None:
        self.s: deque[tuple[float, float | None, float | None]] = deque(maxlen=MAX_SAMPLES)

    def add(self, ts: float, kwh: float | None, watt: float | None = None) -> None:
        last = self.s[-1] if self.s else None
        if last and last[0] >= ts:
            ts = last[0] + 0.001
        if last and kwh is None:
            kwh = last[1]   # nur die Leistung hat sich geändert: Zählerstand bleibt
        if last and watt is None:
            watt = last[2]
        if kwh is None:
            return
        if last and len(self.s) > 1 and last[1] == kwh and last[2] == watt and self.s[-2][1] == kwh and self.s[-2][2] == watt:
            self.s[-1] = (ts, kwh, watt)   # unveränderte Werte: nur den Zeitpunkt nachführen, damit der Verlauf auch über lange Pausen reicht
            return
        self.s.append((ts, kwh, watt))

    def baseline(self, start_ts: float) -> float | None:
        """Zählerstand vor dem Beginn der Ladung (letzter Ruhestand, sonst Stand vor dem Vorlauf)."""
        before = [x for x in self.s if x[0] <= start_ts]
        if not before:
            return None
        base = next((x for x in reversed(before) if x[2] is not None and x[2] < IDLE_WATT), None)
        if base is None:
            base = next((x for x in reversed(before) if x[0] <= start_ts - LEAD_SECONDS), None) or before[0]
        return base[1]

    def energy(self, start_ts: float, end_ts: float) -> float | None:
        """Gelieferte kWh zwischen dem Beginn der Ladung und ihrem Ende; None, wenn der Verlauf nicht reicht."""
        before = [x for x in self.s if x[0] <= start_ts]
        if not before:
            return None
        base = next((x for x in reversed(before) if x[2] is not None and x[2] < IDLE_WATT), None)   # letzter Stand, bei dem die Wallbox noch ruhte
        if base is None:
            base = next((x for x in reversed(before) if x[0] <= start_ts - LEAD_SECONDS), None) or before[0]
        after = [x for x in self.s if x[0] <= end_ts]
        end = after[-1] if after else None
        if end is None or end[0] < base[0]:
            return None
        d = end[1] - base[1]
        return round(d, 3) if d >= 0 else None   # kleiner null: Zähler wurde zurückgesetzt


PLUGGED = {"on", "true", "connected", "plugged", "plugged_in", "plugged in", "charging", "charge_complete", "complete", "finished", "waiting", "ready", "angesteckt", "verbunden", "eingesteckt", "cable_locked", "locked", "preparing", "suspended", "suspendedev", "suspendedevse", "occupied", "paused", "1"}
UNPLUGGED = {"off", "false", "disconnected", "unplugged", "not_connected", "not connected", "nicht verbunden", "abgesteckt", "getrennt", "available", "free", "unlocked", "0", "no_car"}


def parse_plug(state: str | None) -> bool | None:
    """Stecker-Zustand aus dem Text eines Sensors: True angesteckt, False abgesteckt, None unbekannt (unavailable, unbekannter Text)."""
    s = str(state or "").strip().lower()
    if s in PLUGGED:
        return True
    if s in UNPLUGGED:
        return False
    return None


def plausible(wb_kwh: float | None, est_kwh: float | None) -> bool:
    """Passt die Wallbox-Energie zur Schätzung aus dem Füllstand? Ohne Schätzung genügt eine positive Menge."""
    if not wb_kwh or wb_kwh <= 0:
        return False
    if not est_kwh:
        return True
    return RATIO_RANGE[0] <= wb_kwh / est_kwh <= RATIO_RANGE[1]


def overlaps(a_start: float, a_end: float, b_start: float, b_end: float) -> bool:
    return a_start < b_end and b_start < a_end


def shared_conflict(start: float, end: float, others: list[dict[str, Any]]) -> bool:
    """Hat ein anderes Fahrzeug an derselben Wallbox im selben Zeitraum geladen (Einträge oder laufende Vorgänge mit ``ts_start``/``ts``)?"""
    return any(overlaps(start, end, o["ts_start"], o["ts"]) for o in others if o.get("ts_start") and o.get("ts"))
