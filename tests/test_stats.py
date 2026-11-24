"""Verbrauchsrechnung: python tests/test_stats.py"""
import importlib.util, json, pathlib, sys

base = pathlib.Path(__file__).parent.parent
spec = importlib.util.spec_from_file_location("stats", base / "custom_components" / "drive_energy_doc" / "stats.py")
st = importlib.util.module_from_spec(spec); sys.modules["stats"] = st; spec.loader.exec_module(st)


def e(ts, km, q, inc=None, **kw):
    return {"ts": ts, "odometer": km, "quantity": q, "increase": inc, **kw}


def test_full_to_full():
    es = [e(1, 1000, 50, 90), e(2, 1700, 42, 80), e(3, 2400, 49, 85)]
    out = st.add_consumption(es)
    assert out[0]["consumption"] is None
    assert out[1]["consumption"] == 6.0 and out[2]["consumption"] == 7.0


def test_partial_counts_at_next_full():
    es = [e(1, 1000, 50, 90), e(2, 1300, 6, 12), e(3, 1700, 36, 70)]
    out = st.add_consumption(es)
    assert out[1]["consumption"] is None          # Teilbetankung zeigt –
    assert out[2]["consumption"] == 6.0           # (6 + 36) l auf 700 km


def test_extra_ignored():
    es = [e(1, 1000, 50, 90), e(2, 1200, 1, None, kind="extra", item="Öl"), e(3, 1700, 42, 80)]
    out = st.add_consumption(es)
    assert out[1]["consumption"] is None and out[2]["consumption"] == 6.0


def test_unknown_increase_counts_as_full():
    out = st.add_consumption([e(1, 1000, 50), e(2, 1700, 42)])
    assert out[1]["consumption"] == 6.0


def test_level_from_to_used():
    es = [e(1, 1000, 50, None, level_from=10, level_to=100), e(2, 1700, 42, None, level_from=20, level_to=90)]
    assert st.add_consumption(es)[1]["consumption"] == 6.0


def test_real_bmw_import():
    f = base / "migration" / "out" / "import" / "BMW X1" / "entries.json"
    if not f.exists():
        return
    es = json.loads(f.read_text(encoding="utf-8"))
    for x in es:  # wie die Migration: „%“ der alten Tabelle war der Zuwachs
        x["increase"] = x.pop("level_to"); x["level_from"] = None
    out = st.add_consumption(es)
    vals = [x["consumption"] for x in out]
    shown = [v for v in vals if v is not None]
    print("BMW X1:", len(es), "Einträge,", len(shown), "mit Verbrauch;", [round(v, 1) for v in shown])
    assert len(shown) >= 20 and all(2 < v < 20 for v in shown)  # Ausreißer: 12.06. (25,65 l) und fehlender Eintrag 21.02.


def test_match_odometer():
    es = [e(1000, 52508, 54), e(5000, 53235, 46), e(9000, 54140, 52)]
    m = st.match_odometer(es, 54210, 9300)
    assert m["status"] == "ok" and m["entry"]["ts"] == 9000 and m["dt"] == 300 and not m["backwards"]
    assert st.match_odometer(es, 54210, 9000 + 3 * 86400)["status"] == "too_old"
    late = st.match_odometer(es, 54146, 9000 + 3 * 86400)                              # Tage später hochgeladen, Stand fast gleich: gehört zum Eintrag
    assert late["status"] == "ok" and late["entry"]["ts"] == 9000
    assert st.match_odometer([{**x, "odometer_source": "foto"} for x in es], 54146, 9000 + 3 * 86400)["status"] == "too_old"   # hat schon ein Tacho-Foto
    other = st.match_odometer([e(1000, 52508, 54), e(5000, 53235, 46), e(9000, 54140, 52), e(9500, 65000, 40)], 54146, 9600)   # zeitlich nächster Eintrag passt nicht zum Stand
    assert other["status"] == "ok" and other["entry"]["ts"] == 9000
    assert st.match_odometer(es, 55000, 9100)["status"] == "mismatch"               # 860 km Abweichung
    assert st.match_odometer(es, 53000, 9100)["backwards"] or st.match_odometer(es, 53000, 9100)["status"] == "mismatch"
    assert st.match_odometer([], 54210, 9000)["status"] == "none"
    assert st.match_odometer([e(9000, 54140, 5, kind="extra")], 54210, 9000)["status"] == "none"   # Zubehör zählt nicht
    nearest = st.match_odometer([e(1000, 100, 1), e(2000, 150, 1)], 160, 1900)
    assert nearest["entry"]["ts"] == 2000                                            # der zeitlich nächste


def test_km_plausible():
    es = [e(1000, 61000, 40), e(2000, 61700, 40), e(3000, 62400, 40)]
    assert st.km_plausible(es, 62400 + 700, 4000)                 # nächster Tankstand
    assert not st.km_plausible(es, 1192877, 4000)                 # sieben Stellen: Belegnummer
    assert not st.km_plausible(es, 163241, 4000)                  # Sprung über 5000 km
    assert not st.km_plausible(es, 61100, 4000)                   # weit unter dem vorigen Stand
    assert st.km_plausible(es, 61350, 1500)                       # zwischen zwei Einträgen
    assert not st.km_plausible(es, 62000, 1500)                   # über dem nächsten Eintrag
    assert st.km_plausible(es, 54000, None) and not st.km_plausible(es, 200000, None)   # ohne Datum: Abstand zum Mittelwert
    assert st.km_plausible([], 5000, 100) and not st.km_plausible([], 0, 100)


def test_km_rank():
    none, beleg, foto = {"odometer": None}, {"odometer": 1, "odometer_source": "beleg"}, {"odometer": 1, "odometer_source": "foto"}
    sensor, hand, alt = {"odometer": 1, "odometer_source": "sensor"}, {"odometer": 1, "odometer_source": "manuell"}, {"odometer": 1}
    assert all(st.km_better(none, s) for s in ("beleg", "foto", "sensor", "manuell"))                # noch nichts da: jede Quelle darf
    assert st.km_better(beleg, "foto") and not st.km_better(foto, "beleg")                            # Tacho-Foto schlägt Quittung, nie umgekehrt
    assert not st.km_better(sensor, "foto") and not st.km_better(sensor, "beleg")                     # Sensor des Autos schlägt beides
    assert st.km_better(foto, "sensor") and st.km_better(sensor, "manuell")                           # von Hand gesetzt gewinnt immer
    assert not st.km_better(hand, "sensor") and not st.km_better(alt, "foto")                         # alter Eintrag ohne Quelle zählt wie Sensor


def test_phev_chains_are_separate():
    """Plug-in-Hybrid: Kraftstoff (l) und Strom (kWh) haben je eine eigene Verbrauchskette, die Kilometer sind gemeinsam."""
    es = [e(1, 1000, 40, id="a"), e(2, 1100, 10, id="b", energy="electric"), e(3, 1500, 25, id="c"), e(4, 1400, 30, id="d", energy="electric"), e(5, 1900, 20, id="f"), e(6, 1700, 28, id="g", energy="electric")]
    out = {x["id"]: x["consumption"] for x in st.add_consumption(es)}
    assert out["a"] is None and out["b"] is None          # jeweils die erste Betankung der Kette
    assert abs(out["c"] - 25 / 500 * 100) < 0.01          # 25 l auf 500 km (Kraftstoffkette)
    assert abs(out["g"] - 28 / 300 * 100) < 0.01          # 28 kWh auf 300 km seit dem vorigen Laden (Stromkette)
    assert st.energy_of({"energy": "electric"}) == "electric" and st.energy_of({}) == "fuel"


def test_phev_check_consumption_uses_own_chain():
    d = e(5, 2500, 25, id="d")
    es = [e(1, 1000, 40, id="a"), e(2, 1500, 25, id="b"), e(3, 2000, 25, id="c"), e(4, 1200, 15, id="x", energy="electric"), d]
    chk = st.check_consumption(es, d, 2500)
    assert chk and chk["energy"] == "fuel" and abs(chk["cons"] - 5.0) < 0.01 and chk["ok"]


def test_plausibility_warnings_and_missing():
    es = [
        {"id": "a", "ts": 1, "odometer": 1000, "quantity": 40.0, "unit_price": 1.8, "total": 72.0, "consumption": None},
        {"id": "b", "ts": 2, "odometer": 900, "quantity": 2.6, "unit_price": 1.789, "total": 38.64, "consumption": 7.0},        # km zurück, Menge x Preis passt nicht
        {"id": "c", "ts": 3, "odometer": None, "quantity": None, "unit_price": None, "total": None, "consumption": None},           # unvollständig
        {"id": "d", "ts": 4, "odometer": 7000, "quantity": 30.0, "unit_price": 5.0, "total": 150.0, "consumption": 40.0},          # Preis, Sprung, Verbrauch
        {"id": "x", "ts": 5, "kind": "extra", "total": None},
    ]
    w = st.plausibility(es, capacity=50.0)
    assert w["a"] == {}, w["a"]
    assert w["b"]["km"]["k"] == "back" and w["b"]["total"]["k"] == "calc" and abs(w["b"]["total"]["calc"] - 4.65) < 0.01
    assert {w["c"][k]["k"] for k in ("qty", "total", "km", "price")} == {"missing"}
    assert w["d"]["price"]["k"] == "range" and w["d"]["km"]["k"] == "jump" and w["d"]["cons"]["k"] == "range"
    assert w["x"] == {"total": {"k": "missing"}, "km": {"k": "missing"}}, w["x"]   # Zubehör: Betrag und Kilometerstand fehlen
    ex2 = [{"id": "z", "ts": 1, "kind": "extra", "total": 9.5, "odometer": 12118.0, "odometer_source": "bekannt"}]
    assert st.plausibility(ex2, 50.0)["z"] == {}, "Zubehör mit zuletzt bekanntem Stand ist vollständig"
    # Plug-in-Hybrid: sehr niedriger Kraftstoffverbrauch ist erlaubt, beim Strom nicht
    low = [{"id": "f", "ts": 1, "odometer": 1, "quantity": 5.0, "unit_price": 1.8, "total": 9.0, "consumption": 0.8}]
    assert "cons" not in st.plausibility(low, 50.0, 12.0, phev=True)["f"] and "cons" in st.plausibility(low, 50.0)["f"]
    elec = [{"id": "g", "ts": 1, "odometer": 1, "quantity": 10.0, "unit_price": 0.4, "total": 4.0, "consumption": 3.0, "energy": "electric"}]
    assert "cons" in st.plausibility(elec, 50.0, 12.0, phev=True)["g"]


def test_phev_mixed_plausibility():
    """Plug-in-Hybrid im Wechsel Benzin/Strom: der Verbrauch je Energieart wird nicht einzeln geflaggt, nur der gemeinsame."""
    def e(i, ts, km, q, p, en=None, cons=None):
        d = {"id": i, "ts": ts, "odometer": km, "quantity": q, "unit_price": p, "total": round(q * p, 2), "consumption": cons}
        if en:
            d["energy"] = en
        return d
    ok = [e("a", 1, 1000, 40.0, 1.8, cons=None), e("b", 2, 1100, 10.0, 0.4, "electric"), e("c", 3, 1500, 12.0, 1.8, cons=0.5),
          e("d", 4, 1800, 11.0, 0.4, "electric", cons=3.7), e("f", 5, 2200, 8.0, 1.8, cons=0.6)]
    w = st.plausibility(ok, 50.0, 12.0, phev=True)
    assert all("cons" not in w[k] for k in w), w      # 0,5 und 0,6 l/100 km allein wären auffällig, sind hier normal
    bad = [e("a", 1, 1000, 40.0, 1.8), e("b", 2, 1100, 10.0, 0.4, "electric"), e("c", 3, 1500, 60.0, 1.8, cons=15.0),
           e("d", 4, 1800, 11.0, 0.4, "electric", cons=3.7)]   # 60 l + 11 kWh auf 700 km = 85 kWh-Äq./100 km
    wb = st.plausibility(bad, 70.0, 12.0, phev=True)
    assert wb["d"]["cons"]["k"] == "combined" and wb["d"]["cons"]["v"] > 60, wb["d"]
    # fast nur elektrisch gefahren, Benzin die Ausnahme, nicht jede Ladung erfasst: sehr niedriger gemeinsamer Verbrauch ist kein Fehler
    little = [e("a", 1, 1000, 40.0, 1.8), e("b", 2, 1100, 10.0, 0.4, "electric"), e("c", 3, 3100, 2.0, 1.8), e("d", 4, 3600, 6.0, 0.4, "electric")]
    assert all("cons" not in v for v in st.plausibility(little, 70.0, 12.0, phev=True).values())
    # zu kurze Strecke (unter 300 km): keine Aussage
    short = [e("a", 1, 1000, 40.0, 1.8), e("b", 2, 1100, 10.0, 0.4, "electric"), e("c", 3, 1200, 60.0, 1.8)]
    assert "cons" not in st.plausibility(short, 70.0, 12.0, phev=True)["c"]
    # nur Kraftstoff (kein Laden): normale Einzelprüfung mit weitem Bereich nach unten
    only_fuel = [e("a", 1, 1000, 40.0, 1.8), e("b", 2, 1500, 5.0, 1.8, cons=0.5)]
    assert "cons" not in st.plausibility(only_fuel, 50.0, 0.0, phev=True)["b"]


def test_duplicates_flagged():
    a = {"id": "a", "ts": 1, "quantity": 21.6, "unit_price": 1.789, "total": 38.64, "odometer": None, "consumption": None}
    b = {"id": "b", "ts": 900, "quantity": 21.6, "unit_price": 1.789, "total": 38.64, "odometer": 12390, "consumption": None}
    c = {"id": "c", "ts": 500, "quantity": 11.8, "unit_price": 0.52, "total": 6.14, "odometer": 12205, "consumption": None}
    x = {"id": "x", "ts": 600, "kind": "extra", "total": 38.64, "quantity": 21.6}
    w = st.plausibility([a, b, c, x], 50.0)
    assert w["a"]["total"] == {"k": "dup", "other": "b"} and w["b"]["qty"] == {"k": "dup", "other": "a"}, (w["a"], w["b"])
    assert "total" not in w["c"] and "qty" not in w["x"], "anderer Beleg und Zubehör: keine Meldung"


def test_km_plausible_undated_entries_ignored():
    """Ein Eintrag, dessen Datum nur der Upload-Zeitpunkt ist (ts = created), darf einen Tacho mit früherem Aufnahmedatum nicht ablehnen."""
    es = [{"id": "a", "ts": 100.0, "created": 5000.0, "odometer": 12118.0},        # datiert (Beleg), Stand 12118
          {"id": "b", "ts": 9000.0, "created": 9000.0, "odometer": 12205.0}]       # undatiert (Upload), Stand 12205
    assert st.km_plausible(es, 12390.0, ts=500.0), "Stand 12390 nach dem datierten Eintrag: möglich"
    es[1]["created"] = 9000.0 - 50000.0                                            # jetzt ein echt datierter, späterer Eintrag (Datum weit vom Upload entfernt)
    assert not st.km_plausible(es, 12390.0, ts=500.0), "Stand 12390 vor einem späteren Eintrag mit 12205: unmöglich"


def test_duplicate_same_km():
    a = {"id": "a", "ts": 1, "quantity": 17.9, "unit_price": 1.769, "total": 31.67, "odometer": 12760.0, "consumption": None}
    b = {"id": "b", "ts": 900, "quantity": 37.9, "unit_price": 1.769, "total": 67.07, "odometer": 12760.0, "consumption": None}   # Display falsch gelesen, gleicher Kilometerstand
    w = st.plausibility([a, b], 50.0)
    assert w["a"]["km"] == {"k": "dup", "other": "b"} and w["b"]["total"] == {"k": "dup", "other": "a"}, w
    c = dict(b, id="c", energy="electric")
    assert "km" not in st.plausibility([a, c], 50.0, 12.0, phev=True)["a"], "andere Energieart: kein Duplikat"


for n, fn in list(globals().items()):
    if n.startswith("test_"):
        fn(); print("ok", n)


def test_check_consumption():
    def fill(i, ts, km, q, inc=85):
        return {"id": f"e{i}", "ts": ts, "odometer": km, "quantity": q, "increase": inc}
    base = [fill(1, 1, 10000, 50), fill(2, 2, 10700, 49), fill(3, 3, 11400, 49), fill(4, 4, 12100, 49)]
    new = fill(5, 5, None, 49)
    ok = st.check_consumption(base + [new], new, 12800)           # 700 km für 49 l = 7,0 l/100 km
    assert ok and ok["ok"] and abs(ok["cons"] - 7.0) < 0.01 and ok["driven"] == 700
    short = st.check_consumption(base + [new], new, 12300)        # nur 200 km für 49 l: viel zu hoher Verbrauch
    far = st.check_consumption(base + [new], new, 13900)          # 1800 km für 49 l: unmöglich niedrig
    assert short and not short["ok"] and far and not far["ok"]
    partial = fill(6, 6, None, 10, inc=15)                        # Teilbetankung: nicht prüfbar
    assert st.check_consumption(base + [partial], partial, 12400) is None
    assert st.check_consumption(base[:2] + [new], new, 11400) is None   # zu wenige Vergleichswerte


test_check_consumption()
print('ok test_check_consumption')
