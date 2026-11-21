"""Tankerkennung als reine Zustandsmaschine (keine Home-Assistant-Abhängigkeit, daher testbar).

Regeln:
* Ein Tankvorgang beginnt beim ersten Anstieg des Füllstands. Alle weiteren Anstiege
  werden zu demselben Vorgang addiert (kein Eintrag pro Prozentschritt).
* Er gilt erst als Tanken, wenn der Gesamtzuwachs ``min_increase`` (Standard 5 %) erreicht.
  Fällt der Stand vorher wieder, war es Rauschen und der Kandidat wird verworfen.
* Er endet, wenn ``settle_seconds`` lang kein Zuwachs mehr kam UND (bei Verbrennern)
  das Fahrzeug weiter als ``min_distance`` Meter vom Tankort entfernt ist.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import asin, cos, radians, sin, sqrt
from typing import Any

EPS = 0.05
CANDIDATE_TIMEOUT_S = 600


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Entfernung in Metern."""
    p1, p2 = radians(lat1), radians(lat2)
    a = sin((p2 - p1) / 2) ** 2 + cos(p1) * cos(p2) * sin(radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371000 * asin(sqrt(a))


@dataclass
class Pending:
    start_level: float
    level: float
    start_ts: float
    last_increase_ts: float
    lat: float | None = None
    lon: float | None = None
    odometer: float | None = None
    valid: bool = False
    extras: dict[str, Any] = field(default_factory=dict)  # Preis/Station/Beleg, vom Aufrufer befüllt


class FuelDetector:
    """Eine Instanz je Fahrzeug."""

    def __init__(
        self,
        min_increase: float = 5.0,
        settle_seconds: float = 60,
        min_distance: float = 250,
        require_distance: bool = True,
        pending: dict | None = None,
    ) -> None:
        self.min_increase = min_increase
        self.settle_seconds = settle_seconds
        self.min_distance = min_distance
        self.require_distance = require_distance
        self.prev_level: float | None = None
        self.pending: Pending | None = Pending(**pending) if pending else None

    def dump(self) -> dict | None:
        return asdict(self.pending) if self.pending else None

    def on_level(self, level: float, ts: float, pos: tuple[float, float] | None, odometer: float | None) -> str | None:
        """Neuer Füllstand. Rückgabe: 'started', 'valid', 'cancelled' oder None."""
        prev, self.prev_level = self.prev_level, level
        if prev is None:
            return None
        if level > prev + EPS:
            p = self.pending
            if p is None:
                p = self.pending = Pending(
                    start_level=prev, level=level, start_ts=ts, last_increase_ts=ts,
                    lat=pos[0] if pos else None, lon=pos[1] if pos else None, odometer=odometer,
                )
                event = "started"
            else:
                p.level = level
                p.last_increase_ts = ts
                event = None
                if p.lat is None and pos:  # Position erst später bekannt geworden
                    p.lat, p.lon = pos
                if p.odometer is None:
                    p.odometer = odometer
            if not p.valid and p.level - p.start_level >= self.min_increase:
                p.valid = True
                return "valid"
            return event
        if level < prev - EPS and self.pending and not self.pending.valid:
            self.pending = None  # Stand fällt wieder: Rauschen / Fahrt, kein Tanken
            return "cancelled"
        return None

    def check(self, ts: float, pos: tuple[float, float] | None) -> dict | None:
        """Periodisch aufrufen. Liefert den fertigen Tankvorgang oder None."""
        p = self.pending
        if p is None:
            return None
        if not p.valid:
            if ts - p.last_increase_ts > CANDIDATE_TIMEOUT_S:
                self.pending = None
            return None
        if ts - p.last_increase_ts < self.settle_seconds:
            return None
        if self.require_distance:
            if pos is None or p.lat is None or haversine_m(p.lat, p.lon, pos[0], pos[1]) <= self.min_distance:
                return None
        done = asdict(p)
        self.pending = None
        return done
