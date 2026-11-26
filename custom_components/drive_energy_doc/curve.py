"""Ladekurve: während einer Ladung einmal pro Minute Leistung und Ladestand merken und je Eintrag als eigene Datei ablegen (reine Funktionen, testbar).

Ein Punkt ist [Zeit (s), Wallbox-Leistung (W), Leistung laut Auto (W), Ladestand (%)]; fehlende Werte sind None.
Die Datei liegt unter config/drive_energy_doc/<Fahrzeug>/curves/<Eintrag>.json und wird nur geladen, wenn das Panel die Kurve zeigt.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

STEP_S = 60          # Abstand der Punkte
MAX_POINTS = 1500    # darüber wird jeder zweite Punkt verworfen (lange Ladungen mit Pausen)


def add(points: list[list], ts: float, wb_w: float | None, car_w: float | None, soc: float | None) -> bool:
    """Punkt anhängen, wenn seit dem letzten mindestens STEP_S vergangen sind. Rückgabe: angehängt?"""
    if points and ts - points[-1][0] < STEP_S:
        return False
    points.append([round(ts), _r(wb_w, 0), _r(car_w, 0), _r(soc, 1)])
    if len(points) > MAX_POINTS:
        del points[1:-1:2]   # erster und letzter Punkt bleiben
    return True


def _r(v: float | None, nd: int) -> float | int | None:
    if v is None:
        return None
    return round(v) if nd == 0 else round(v, nd)


def payload(points: list[list]) -> dict[str, Any]:
    """Kompakte Form zum Speichern: Startzeit und Abstände in Sekunden."""
    t0 = points[0][0] if points else 0
    return {"v": 1, "t0": t0, "p": [[p[0] - t0, p[1], p[2], p[3]] for p in points]}


def write(path: Path, points: list[list]) -> None:
    """Executor: Datei schreiben (Ordner bei Bedarf anlegen)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload(points), separators=(",", ":")), encoding="utf-8")


def read(path: Path) -> dict[str, Any] | None:
    """Executor: gespeicherte Kurve oder None."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def restore(data: dict[str, Any] | None) -> list[list]:
    """Gespeicherte Kurve wieder als Punktliste mit absoluten Zeiten (laufende Ladung nach einem Neustart)."""
    if not data or not data.get("p"):
        return []
    t0 = data.get("t0", 0)
    return [[p[0] + t0, p[1], p[2], p[3]] for p in data["p"]]


def idle(p: list | None) -> bool:
    """Punkt ohne Lieferung (Wallbox und Auto unter 50 W oder unbekannt)."""
    return p is not None and (p[1] or 0) < 50 and (p[2] or 0) < 50


def skip_idle(points: list[list], ts: float, wb_w: float | None, car_w: float | None, soc: float | None) -> bool:
    """In längeren Pausen nur alle 15 Minuten einen Punkt (gleicher Ladestand, keine Leistung)."""
    last = points[-1] if points else None
    return bool(last) and idle(last) and idle([ts, wb_w, car_w, soc]) and last[3] == (round(soc, 1) if soc is not None else None) and ts - last[0] < 900


def trim(points: list[list]) -> list[list]:
    """Ruhe nach dem Ende der Lieferung abschneiden (die Ladung bleibt bis zum Wegfahren offen); ein Ruhepunkt bleibt als Ende."""
    last = max((i for i, p in enumerate(points) if not idle(p)), default=None)
    return points if last is None else points[: last + 2]
