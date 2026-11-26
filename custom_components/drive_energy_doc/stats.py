"""Verbrauchsrechnung (reine Funktionen, ohne Home-Assistant-Abhängigkeit, daher testbar).

Methode: Voll-zu-Voll. Eine Betankung zählt als „voll“, wenn der Zuwachs mindestens ``full_increase`` Prozent
beträgt (wie in der alten Tankkontrolle: unter 30 % = Teilbetankung). Teilbetankungen zeigen keinen Verbrauch
und werden bei der nächsten vollen mitgerechnet. Zubehör (kind == "extra") zählt nicht.
Ist über den Zuwachs nichts bekannt (z. B. von Hand angelegt), gilt die Betankung als voll.
"""

from __future__ import annotations

from typing import Any

FULL_INCREASE = 30.0  # Prozent Zuwachs, ab dem eine Betankung als „voll“ gilt


def energy_of(e: dict[str, Any]) -> str:
    """Energieart eines Eintrags: ``electric`` (Strom, kWh) oder ``fuel`` (Kraftstoff, l). Nur beim Plug-in-Hybrid kommen beide vor."""
    return "electric" if e.get("energy") == "electric" else "fuel"


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
    chains: dict[str, list] = {}   # Plug-in-Hybrid: Kraftstoff und Strom haben je eine eigene Kette (Menge in l bzw. kWh), sonst nur eine
    for src in sorted(entries, key=lambda x: x["ts"]):
        e = dict(src)
        e["consumption"] = None
        out.append(e)
        if e.get("kind") == "extra":
            continue
        ch = chains.setdefault(energy_of(e), [0.0, None])
        ch[0] += e.get("quantity") or 0
        if e.get("odometer") is None or not is_full(e, full_increase):
            continue
        if ch[1] is not None and e["odometer"] > ch[1] and ch[0] > 0:
            e["consumption"] = round(ch[0] / (e["odometer"] - ch[1]) * 100, 2)
            e["cons_km"] = round(e["odometer"] - ch[1], 1)   # Strecke, auf die sich der Verbrauch bezieht (für gewichtete Mittel)
        ch[0], ch[1] = 0.0, e["odometer"]
    return out


def match_odometer(entries: list[dict[str, Any]], km: float, sent_ts: float, window: float = 24 * 3600, tolerance: float = 300.0, near_km: float = 50.0) -> dict[str, Any]:
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
    # Passt der Stand fast genau (bis near_km) zu einem Eintrag, der noch kein Tacho-Foto hat, gehört er dorthin: das gilt vor der Uhrzeit
    # (Fotos werden oft später hochgeladen, oder der zeitlich nächste Eintrag ist ein anderer Tankvorgang)
    near = [x for x in fuel if x.get("odometer") is not None and x.get("odometer_source") != "foto" and abs(km - x["odometer"]) <= near_km]
    if near and not (e in near and abs(dt) <= window):
        e = min(near, key=lambda x: (abs(km - x["odometer"]), -x["ts"]))
        dt = sent_ts - e["ts"]
        prev = [x["odometer"] for x in fuel if x["ts"] < e["ts"] and x.get("odometer") is not None]
        prev_odo = max(prev) if prev else None
        return {"status": "ok", "entry": e, "dt": dt, "prev_odo": prev_odo, "backwards": prev_odo is not None and km < prev_odo}
    if abs(dt) > window:
        return {"status": "too_old", "entry": e, "dt": dt}
    prev = [x["odometer"] for x in fuel if x["ts"] < e["ts"] and x.get("odometer") is not None]
    prev_odo = max(prev) if prev else None
    od = e.get("odometer")
    status = "mismatch" if od is not None and abs(km - od) > tolerance else "ok"
    return {"status": status, "entry": e, "dt": dt, "prev_odo": prev_odo, "backwards": prev_odo is not None and km < prev_odo}


def check_consumption(entries: list[dict[str, Any]], entry: dict[str, Any], km: float, tolerance: float = 0.4, full_increase: float = FULL_INCREASE) -> dict[str, Any] | None:
    """Plausibilität eines Kilometerstands zu einem Tankvorgang: Verbrauch seit der letzten vollen Betankung gegen den bisherigen Durchschnitt.

    Die getankte Menge (plus Teilbetankungen dazwischen) geteilt durch die gefahrenen Kilometer ergibt den Verbrauch; weicht er um mehr als
    ``tolerance`` (40 %) vom Durchschnitt der letzten fünf Voll-zu-Voll-Werte ab, ist ``ok`` falsch. None = nicht prüfbar (Teilbetankung, keine
    Menge, keine frühere Betankung mit Kilometerstand oder weniger als zwei Vergleichswerte).
    """
    mine = energy_of(entry)
    fuel = sorted((e for e in entries if e.get("kind") != "extra" and energy_of(e) == mine), key=lambda x: x["ts"])
    idx = next((i for i, e in enumerate(fuel) if e["id"] == entry["id"]), None)
    q = entry.get("quantity")
    if idx is None or not q or not is_full(entry, full_increase):
        return None
    j = next((i for i in range(idx - 1, -1, -1) if fuel[i].get("odometer") is not None and is_full(fuel[i], full_increase)), None)
    if j is None:
        return None
    prev_odo = float(fuel[j]["odometer"])
    driven = float(km) - prev_odo
    if driven <= 0:
        return None
    litres = sum((x.get("quantity") or 0) for x in fuel[j + 1: idx + 1])
    others = [e["consumption"] for e in add_consumption([x for x in entries if x["id"] != entry["id"]], full_increase) if e.get("consumption") and energy_of(e) == mine][-5:]
    if len(others) < 2 or litres <= 0:
        return None
    avg = sum(others) / len(others)
    cons = litres / driven * 100
    dev = abs(cons - avg) / avg
    return {"prev_odo": prev_odo, "driven": driven, "litres": litres, "cons": cons, "avg": avg, "dev": dev, "ok": dev <= tolerance, "energy": mine}


def km_plausible(entries: list[dict[str, Any]], km: float | None, ts: float | None = None, exclude: str | None = None, max_jump: float = 5000.0, back_tol: float = 50.0) -> bool:
    """Ist ein von der KI gelesener Kilometerstand möglich? (Belegnummern, Säulen- oder Kartennummern werden gern fälschlich als Kilometerstand gelesen.)

    Immer: größer als 0 und höchstens sechs Stellen. Mit Zeitpunkt ``ts`` (Datum vom Beleg): der Stand darf nicht unter dem des zeitlich vorigen Eintrags
    liegen (Toleranz ``back_tol``), nicht über dem des nächsten, und nicht mehr als ``max_jump`` km über dem vorigen (mehr schafft ein Tank nicht).
    Ohne Zeitpunkt: nicht weiter als 80 000 km vom mittleren Stand der übrigen Einträge entfernt.
    """
    if km is None or km <= 0 or km > 999999:
        return False
    fuel = sorted((e for e in entries if e.get("kind") != "extra" and e.get("odometer") and (exclude is None or e.get("id") != exclude)), key=lambda x: x["ts"])
    if ts is not None:
        # Ein Eintrag, dessen Datum nur der Zeitpunkt des Uploads ist (angelegt aus Säulen-Foto und Tacho, ts nahe created), sagt nichts über die Reihenfolge: nicht als „späterer“ Eintrag zählen
        undated = lambda e: e.get("created") is not None and abs(e["ts"] - e["created"]) < 3 * 3600   # noqa: E731
        prev = [e for e in fuel if e["ts"] <= ts]
        nxt = [e for e in fuel if e["ts"] > ts and not undated(e)]
        if prev and (km < prev[-1]["odometer"] - back_tol or km > prev[-1]["odometer"] + max_jump):
            return False
        if nxt and km > nxt[0]["odometer"] + back_tol:
            return False
        return True
    odos = sorted(e["odometer"] for e in fuel)
    return not (len(odos) >= 3 and abs(km - odos[len(odos) // 2]) > 80000)


# Rangfolge der Quellen eines Kilometerstands: die Entität des Autos ist immer die beste, dann das Foto vom Tacho, erst dann der Stand auf der Quittung
# (der wird oft von Hand eingegeben und kann falsch sein). Ein von Hand eingetragener Stand (Panel oder getippt) gilt als bewusste Entscheidung und gewinnt immer.
KM_RANK = {"bekannt": 0.5, "beleg": 1, "foto": 2, "sensor": 3, "manuell": 4}   # „bekannt“ = nur der zuletzt bekannte Stand (bei Zubehör), jede echte Quelle ersetzt ihn


def km_rank(entry: dict[str, Any]) -> int:
    """0 = noch kein Kilometerstand; ältere Einträge ohne Quellenangabe zählen wie der Sensor."""
    if entry.get("odometer") is None:
        return 0
    return KM_RANK.get(entry.get("odometer_source"), KM_RANK["sensor"])


def km_better(entry: dict[str, Any], source: str) -> bool:
    """Darf ein Kilometerstand aus ``source`` den vorhandenen des Eintrags ersetzen (oder setzen)?"""
    return KM_RANK[source] > km_rank(entry)


def plausibility(entries: list[dict[str, Any]], capacity: float = 0.0, capacity_el: float = 0.0, phev: bool = False, ev: bool = False) -> dict[str, dict[str, dict[str, Any]]]:
    """Unplausible Werte je Eintrag, für die Warndreiecke in der Liste. Rückgabe: ``{Eintrags-ID: {Spalte: Hinweis}}`` mit den Spalten qty, price, total, km, cons.
    Fehlende Angaben (Menge, Betrag, Kilometerstand, bei Zubehör der Betrag) werden als ``missing`` gemeldet. Geprüft werden: Menge x Preis gegen Betrag, ein ungewöhnlicher Preis je Einheit, eine Menge über dem Tank bzw. Akku, ein Kilometerstand unter dem vorigen oder
    mehr als 5000 km darüber, ein ungewöhnlicher Verbrauch (Plug-in-Hybrid: der Kraftstoff darf sehr niedrig sein). ``entries`` mit Feld ``consumption`` (add_consumption)."""
    out: dict[str, dict[str, dict[str, Any]]] = {}
    last_km: float | None = None
    # Plug-in-Hybrid mit Tanken UND Laden: gefahren wird im Wechsel mit Benzin und Strom, der Verbrauch je Energieart schwankt daher stark und sagt allein nichts.
    # Dann wird nur der gemeinsame Verbrauch geprüft (siehe unten), nicht der einzelner Einträge.
    mixed = phev and len({energy_of(x) for x in entries if x.get("kind") != "extra"}) > 1
    for e in sorted(entries, key=lambda x: x["ts"]):
        w: dict[str, dict[str, Any]] = {}
        out[e["id"]] = w
        if e.get("kind") == "extra":
            if not e.get("total"):
                w["total"] = {"k": "missing"}   # Zubehör ohne Betrag
            if e.get("odometer") is None:
                w["km"] = {"k": "missing"}
            continue
        electric = ev or energy_of(e) == "electric"
        q, p, tot = e.get("quantity"), e.get("unit_price"), e.get("total")
        for col, val in (("qty", q), ("total", tot), ("km", e.get("odometer"))):   # unvollständig: Angabe fehlt (Fragezeichen)
            if not val:
                w[col] = {"k": "missing"}
        if not p and not (q and tot):
            w["price"] = {"k": "missing"}
        if q and p and tot and abs(q * p - tot) > 0.05 + 0.0005 * q:
            hint = {"k": "calc", "q": q, "p": p, "calc": round(q * p, 2), "t": tot}
            w["qty"] = w["price"] = w["total"] = hint
        lo, hi = (0.05, 1.5) if electric else (0.8, 3.5)
        if p and not lo <= p <= hi and "price" not in w:
            w["price"] = {"k": "range", "v": p, "lo": lo, "hi": hi}
        cap = capacity_el if (phev and energy_of(e) == "electric") else capacity
        if q and cap and q > cap * 1.15 and "qty" not in w:
            w["qty"] = {"k": "cap", "v": q, "cap": cap}
        od = e.get("odometer") if e.get("odometer_source") != "bekannt" else None   # geschätzte Stände nicht prüfen
        if od is not None:
            if last_km is not None:
                if od < last_km - 1:
                    w["km"] = {"k": "back", "prev": last_km}
                elif od - last_km > 5000:
                    w["km"] = {"k": "jump", "d": od - last_km}
            last_km = od if last_km is None else max(last_km, od)
        c = e.get("consumption")
        if c and not mixed:
            lo, hi = (6.0, 45.0) if electric else ((0.1, 25.0) if phev else (1.5, 25.0))
            if not lo <= c <= hi:
                w["cons"] = {"k": "range", "v": c, "lo": lo, "hi": hi}
    if mixed:
        _combined_consumption(entries, out)
    _flag_duplicates(entries, out)
    return out


KWH_PER_LITRE = 9.7   # Energiegehalt von Benzin, um Liter und kWh in einem gemeinsamen Verbrauch zu rechnen
COMBINED_RANGE = (0.0, 60.0)   # kWh-Äquivalent je 100 km; ein Plug-in-Hybrid liegt je nach Fahrweise grob zwischen 15 und 40. Nur zu HOHE Werte werden gemeldet: ein niedriger Wert ist
# normal, weil Benzin oft die Ausnahme ist und nicht jede Ladung (z. B. zu Hause) erfasst wird


def _combined_consumption(entries: list[dict[str, Any]], out: dict[str, dict[str, dict[str, Any]]]) -> None:
    """Gemeinsamer Verbrauch aus Kraftstoff und Strom seit dem Punkt, ab dem beide Energiearten bekannt sind (Voll-zu-Voll je Art), umgerechnet in kWh je 100 km.
    Gemeldet wird erst ab 300 km Strecke; der Hinweis steht am Eintrag, bei dem der gemeinsame Wert unplausibel wird."""
    seen: set[str] = set()
    base_km: float | None = None
    energy = 0.0
    armed = False
    for e in sorted((x for x in entries if x.get("kind") != "extra"), key=lambda x: x["ts"]):
        en = energy_of(e)
        od = e.get("odometer") if e.get("odometer_source") != "bekannt" else None
        if not armed:
            seen.add(en)
            if len(seen) == 2:
                armed = True       # ab hier zählt die Menge der folgenden Einträge; Grundlinie ist der nächste bekannte Kilometerstand
                base_km = od
            continue
        if base_km is None:
            if od is not None:
                base_km = od
            continue
        energy += (e.get("quantity") or 0) * (KWH_PER_LITRE if en == "fuel" else 1.0)
        if od is not None and od - base_km >= 300 and energy > 0:
            c = energy / (od - base_km) * 100
            if not COMBINED_RANGE[0] <= c <= COMBINED_RANGE[1]:
                out[e["id"]]["cons"] = {"k": "combined", "v": round(c, 1), "lo": COMBINED_RANGE[0], "hi": COMBINED_RANGE[1]}


def _flag_duplicates(entries: list[dict[str, Any]], out: dict[str, dict[str, dict[str, Any]]]) -> None:
    """Zwei Einträge derselben Energieart mit gleicher Menge und gleichem Betrag sind sehr wahrscheinlich derselbe Beleg zweimal: beide bekommen ein Warndreieck in Menge, Preis und Betrag
    (Hinweis auf den jeweils zeitlich nächsten anderen). Zubehör zählt nicht."""
    groups: dict[tuple, list[dict[str, Any]]] = {}
    for e in sorted(entries, key=lambda x: x["ts"]):
        q, tot = e.get("quantity"), e.get("total")
        if e.get("kind") == "extra" or not (q and tot):
            continue
        groups.setdefault((energy_of(e), round(q, 2), round(tot, 2)), []).append(e)
    for grp in groups.values():
        if len(grp) < 2:
            continue
        for e in grp:
            other = min((x for x in grp if x is not e), key=lambda x: abs(x["ts"] - e["ts"]))
            hint = {"k": "dup", "other": other["id"]}
            for col in ("qty", "price", "total"):
                out[e["id"]].setdefault(col, hint)
    # Derselbe Kilometerstand bei zwei Tank-/Ladevorgängen derselben Energieart: unmöglich, ein Vorgang ist doppelt (auch wenn Menge und Betrag wegen eines falsch gelesenen Displays abweichen)
    by_km: dict[tuple, list[dict[str, Any]]] = {}
    for e in sorted(entries, key=lambda x: x["ts"]):
        if e.get("kind") != "extra" and e.get("odometer") and e.get("odometer_source") != "bekannt":
            by_km.setdefault((energy_of(e), round(float(e["odometer"]))), []).append(e)
    for grp in by_km.values():
        if len(grp) < 2:
            continue
        for e in grp:
            other = min((x for x in grp if x is not e), key=lambda x: abs(x["ts"] - e["ts"]))
            hint = {"k": "dup", "other": other["id"]}
            for col in ("km", "qty", "price", "total"):
                out[e["id"]].setdefault(col, hint)
