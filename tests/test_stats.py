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
