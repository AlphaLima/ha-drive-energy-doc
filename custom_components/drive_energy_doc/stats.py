"""Verbrauchsrechnung (reine Funktionen, ohne Home-Assistant-Abhängigkeit, daher testbar).

Methode: Voll-zu-Voll. Eine Betankung zählt als „voll“, wenn der Zuwachs mindestens ``full_increase`` Prozent
beträgt (wie in der alten Tankkontrolle: unter 30 % = Teilbetankung). Teilbetankungen zeigen keinen Verbrauch
und werden bei der nächsten vollen mitgerechnet. Zubehör (kind == "extra") zählt nicht.
Ist über den Zuwachs nichts bekannt (z. B. von Hand angelegt), gilt die Betankung als voll.
"""

from __future__ import annotations

from typing import Any

FULL_INCREASE = 30.0  # Prozent Zuwachs, ab dem eine Betankung als „voll“ gilt


def increase_of(e: dict[str, Any]) -> float | None:
    """Zuwachs in Prozent: gespeichert (Import) oder aus Füllstand vorher/nachher."""
    if e.get("increase") is not None:
        return float(e["increase"])
    if e.get("level_from") is not None and e.get("level_to") is not None:
        return float(e["level_to"]) - float(e["level_from"])
    return None


def is_full(e: dict[str, Any], full_increase: float = FULL_INCREASE) -> bool:
    inc = increase_of(e)
    return True if inc is None else inc >= full_increase


def add_consumption(entries: list[dict[str, Any]], full_increase: float = FULL_INCREASE) -> list[dict[str, Any]]:
    """Kopien der Einträge (nach Zeit sortiert) mit Feld ``consumption`` (Einheit je 100 km oder None)."""
    out: list[dict[str, Any]] = []
    acc, last_full = 0.0, None
    for src in sorted(entries, key=lambda x: x["ts"]):
        e = dict(src)
        e["consumption"] = None
        out.append(e)
        if e.get("kind") == "extra":
            continue
        acc += e.get("quantity") or 0
        if e.get("odometer") is None or not is_full(e, full_increase):
            continue
        if last_full is not None and e["odometer"] > last_full and acc > 0:
            e["consumption"] = round(acc / (e["odometer"] - last_full) * 100, 2)
        last_full, acc = e["odometer"], 0.0
    return out


def match_odometer(entries: list[dict[str, Any]], km: float, sent_ts: float, window: float = 24 * 3600, tolerance: float = 300.0) -> dict[str, Any]:
    """Einen Tacho-Kilometerstand dem Tankvorgang zuordnen, der zur Sendezeit am besten passt.

    status: none (kein Eintrag), too_old (nächster Tankvorgang liegt außerhalb des Zeitfensters),
    mismatch (Kilometerstand weicht mehr als ``tolerance`` km vom gespeicherten ab), ok.
    ``backwards``: der Wert ist kleiner als beim vorigen Tanken (unplausibel).
    """
    fuel = [e for e in entries if e.get("kind") != "extra"]
    if not fuel:
        return {"status": "none"}
    e = min(fuel, key=lambda x: abs(x["ts"] - sent_ts))
    dt = sent_ts - e["ts"]  # positiv: Nachricht kam nach dem Tanken
    if abs(dt) > window:
        return {"status": "too_old", "entry": e, "dt": dt}
    prev = [x["odometer"] for x in fuel if x["ts"] < e["ts"] and x.get("odometer") is not None]
    prev_odo = max(prev) if prev else None
    od = e.get("odometer")
    status = "mismatch" if od is not None and abs(km - od) > tolerance else "ok"
    return {"status": status, "entry": e, "dt": dt, "prev_odo": prev_odo, "backwards": prev_odo is not None and km < prev_odo}
