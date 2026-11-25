"""Schätzung, Korrekturfaktor und Ladeart (AC/DC): python tests/test_charge.py"""
import importlib.util
import pathlib
import sys

base = pathlib.Path(__file__).parent.parent
spec = importlib.util.spec_from_file_location("charge", base / "custom_components" / "drive_energy_doc" / "charge.py")
ch = importlib.util.module_from_spec(spec)
sys.modules["charge"] = ch
spec.loader.exec_module(ch)


def e(q, lf=20, lt=70, src="beleg", **kw):
    return {"ts": 1, "energy": "electric", "quantity": q, "quantity_source": src, "level_from": lf, "level_to": lt, **kw}


def test_parse_type():
    assert ch.parse_type("DC") == "dc" and ch.parse_type("CCS") == "dc" and ch.parse_type("Schnellladen") == "dc"
    assert ch.parse_type("AC") == "ac" and ch.parse_type("Type 2 Wechselstrom") == "ac"
    assert ch.parse_type("AC/DC") is None            # widersprüchlich
    assert ch.parse_type("unknown") is None and ch.parse_type("") is None and ch.parse_type(None) is None
    assert ch.parse_type("DC Ladung aktiv") == "dc"


def test_est_quantity_from_levels():
    assert ch.est_quantity(e(40), 60) == 30.0                      # 50 % von 60 kWh
    assert ch.est_quantity(e(40, est_quantity=33.0), 60) == 33.0   # gespeicherte Schätzung geht vor
    assert ch.est_quantity({"level_from": None, "level_to": None}, 60) is None
    assert ch.est_quantity(e(40, lf=70, lt=20), 60) is None        # kein Zuwachs


def test_factor_needs_three_samples_and_uses_median():
    es = [e(27), e(27.6)]                                           # Schätzung je 30 kWh: Faktor 0,9 und 0,92
    assert ch.factor(es, "electric", 60)[0] is None                 # nur zwei Einträge
    es.append(e(33))                                                # 1,1: Ausreißer, Median bleibt 0,92
    f, n, grp = ch.factor(es, "electric", 60)
    assert f == 0.92 and n == 3 and grp == "all"


def test_factor_ignores_unreasonable_and_non_receipt():
    es = [e(27), e(27), e(27), e(90), e(5), e(20, src="berechnet"), e(20, src="manuell")]   # 3,0 und 0,17 liegen außerhalb, die letzten beiden haben keinen Beleg
    f, n, _ = ch.factor(es, "electric", 60)
    assert f == 0.9 and n == 3


def test_factor_by_type_with_fallback():
    es = [e(27, charge_type="ac")] * 3 + [e(24, charge_type="dc")] * 2    # AC 0,9; DC nur zwei Einträge
    assert ch.factor(es, "electric", 60, "ac")[:3] == (0.9, 3, "ac")
    f, n, grp = ch.factor(es, "electric", 60, "dc")                       # DC zu wenig: alle zusammen
    assert grp == "all" and n == 5 and f == 0.9
    assert ch.factor(es, "electric", 60, None)[2] == "all"


def test_kinds_do_not_mix():
    fuel = {"ts": 1, "quantity": 40, "quantity_source": "beleg", "level_from": 10, "level_to": 90}
    es = [fuel] * 3 + [e(27)] * 3
    assert ch.factor(es, "fuel", 50)[0] == 1.0 and ch.factor(es, "electric", 60)[0] == 0.9


def test_classify_priority():
    assert ch.classify("dc", 7000, 5, 11) == ("dc", "sensor", 7.0)           # Sensor geht vor der Leistung
    assert ch.classify(None, 50000, None, 11) == ("dc", "leistung", 50.0)
    assert ch.classify(None, 10800, None, 11)[:2] == ("ac", "leistung")      # unter der Grenze mit Spielraum
    assert ch.classify(None, 12200, None, 11)[:2] == ("dc", "leistung")      # über 11 kW mal 1,1
    assert ch.classify(None, 12200, None, 22)[:2] == ("ac", "leistung")      # Auto mit 22 kW AC
    assert ch.classify(None, None, 80, 11) == ("dc", "mittel", 80.0)
    t, s, kw = ch.classify(None, None, 6, 11)                                # mittlere Leistung beweist nie AC
    assert t is None and s is None and kw == 6.0
    assert ch.classify(None, None, None, None) == (None, None, None)


def test_avg_power():
    assert ch.avg_power_kw(40, 0, 1800, 60) == 80.0                          # 40 kWh in 30 min
    assert ch.avg_power_kw(40, 0, 120, 60) is None                           # unter 5 Minuten
    assert ch.avg_power_kw(2, 0, 3600, 3) is None                            # unter 5 Prozent
    assert ch.avg_power_kw(None, 0, 3600, 60) is None


for name in [n for n in dir() if n.startswith("test_")]:
    globals()[name]()
    print("ok", name)
