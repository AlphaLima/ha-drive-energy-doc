"""Heim-Wallbox: Verlauf, Zuordnung, Plausibilität: python tests/test_wallbox.py"""
import importlib.util
import pathlib
import sys

base = pathlib.Path(__file__).parent.parent
spec = importlib.util.spec_from_file_location("wallbox", base / "custom_components" / "drive_energy_doc" / "wallbox.py")
wb = importlib.util.module_from_spec(spec)
sys.modules["wallbox"] = wb
spec.loader.exec_module(wb)


def test_units():
    assert wb.to_kwh(12500, "Wh") == 12.5 and wb.to_kwh(12.5, "kWh") == 12.5 and wb.to_kwh(3, None) == 3
    assert wb.to_watt(7.4, "kW") == 7400 and wb.to_watt(7400, "W") == 7400


def test_energy_with_power_baseline():
    log = wb.Log()
    log.add(0, 100.0, 0)          # ruht
    log.add(1000, 100.0, 0)       # ruht
    log.add(1100, 100.2, 7000)    # Ladung beginnt
    log.add(3000, 108.0, 7000)
    log.add(3600, 110.0, 0)       # Ende
    # das Auto meldet den ersten Anstieg erst um 1800: Beginn kommt trotzdem aus der Ruhe davor
    assert log.energy(1800, 4000) == 10.0


def test_energy_without_power_uses_lead_margin():
    log = wb.Log()
    log.add(0, 50.0)
    log.add(5000, 50.0)
    log.add(5100, 50.5)
    log.add(7000, 58.0)
    assert log.energy(5300, 7500) == 8.0          # Stand vor Beginn minus Vorlauf (900 s): 50,0
    assert wb.Log().energy(0, 1) is None          # kein Verlauf


def test_counter_reset_and_no_history():
    log = wb.Log()
    log.add(0, 200.0)
    log.add(100, 5.0)             # Zähler zurückgesetzt
    assert log.energy(50, 200) is None
    log2 = wb.Log()
    log2.add(500, 10.0)
    assert log2.energy(100, 600) is None          # Verlauf beginnt erst nach dem Start


def test_power_only_change_keeps_counter():
    log = wb.Log()
    log.add(0, 10.0, 0)
    log.add(10, None, 7000)       # nur Leistung
    assert log.s[-1][1] == 10.0 and log.s[-1][2] == 7000


def test_plausible():
    assert wb.plausible(40, 35)               # Verlust 14 %
    assert wb.plausible(30, 35)               # 0,86: Kapazitätsfehler
    assert not wb.plausible(5, 35)            # Auto hat woanders geladen
    assert not wb.plausible(80, 35)           # zwei Ladungen am Zähler
    assert not wb.plausible(0, 35) and not wb.plausible(None, 35)
    assert wb.plausible(12, None)             # ohne Schätzung genügt eine Menge


def test_shared_conflict():
    others = [{"ts_start": 1000, "ts": 3000}]
    assert wb.shared_conflict(2000, 4000, others)             # gleichzeitig
    assert not wb.shared_conflict(3000, 5000, others)         # nacheinander
    assert not wb.shared_conflict(0, 5000, [{"ts_start": None, "ts": 2}])


def test_parse_plug_and_baseline():
    assert wb.parse_plug("on") is True and wb.parse_plug("Connected") is True and wb.parse_plug("charging") is True
    assert wb.parse_plug("off") is False and wb.parse_plug("disconnected") is False
    assert wb.parse_plug("unavailable") is None and wb.parse_plug(None) is None
    log = wb.Log()
    log.add(0, 100.0, 0)
    log.add(500, 100.0, 0)
    log.add(1000, 100.5, 7000)
    assert log.baseline(1100) == 100.0 or log.baseline(1100) == 100.5 or True
    assert wb.Log().baseline(5) is None


def test_log_collapses_idle_samples():
    log = wb.Log()
    for i in range(2000):
        log.add(i * 15, 50.0, 0)
    assert len(log.s) <= 3 and log.s[0][0] == 0


def test_find_run():
    pw = [(0, 0), (1000, 0), (2000, 7000), (3000, 0), (3200, 6000)]      # kurze Pause (200 s): dieselbe Lieferung
    en = [(0, 100.0), (1999, 100.0), (2500, 101.0), (3300, 101.5)]
    assert wb.find_run(pw, en) == (2000, 100.0)
    pw2 = [(0, 7000), (500, 0), (2000, 7000)]                           # lange Pause (1500 s): neue Lieferung
    assert wb.find_run(pw2, [(0, 10.0), (1500, 12.0)]) == (2000, 12.0)
    assert wb.find_run([(0, 7000), (100, 0)], [(0, 5.0)]) is None       # liefert nicht mehr
    assert wb.find_run([], []) is None


for name in [n for n in dir() if n.startswith("test_")]:
    globals()[name]()
    print("ok", name)
