"""Läuft ohne Home Assistant: python tests/test_detector.py"""

import importlib.util
import pathlib

spec = importlib.util.spec_from_file_location(
    "detector", pathlib.Path(__file__).parent.parent / "custom_components" / "drive_energy_doc" / "detector.py"
)
import sys
det = importlib.util.module_from_spec(spec)
sys.modules["detector"] = det
spec.loader.exec_module(det)

HOME = (51.7300, 6.2900)
FAR = (51.7300, 6.2960)  # ca. 420 m weiter


def new(**kw):
    d = det.FuelDetector(**kw)
    d.on_level(40, 0, HOME, 1000)
    return d


def test_single_fill_counted_once():
    d = new()
    # Zapfvorgang in vielen kleinen Schritten
    events = [d.on_level(40 + i * 2, 10 + i * 5, HOME, 1000) for i in range(1, 25)]
    assert events.count("started") == 1 and events.count("valid") == 1
    assert d.pending.level == 88
    # direkt nach dem Zapfen: noch am Ort, keine Beendigung
    assert d.check(200, HOME) is None
    # 1 Min. ruhig, aber noch am Tankort: nicht beendet
    assert d.check(10 + 24 * 5 + 61, HOME) is None
    # 1 Min. ruhig und >250 m weg: beendet, genau ein Eintrag
    done = d.check(10 + 24 * 5 + 61, FAR)
    assert done and done["start_level"] == 40 and done["level"] == 88 and done["odometer"] == 1000
    assert d.pending is None and d.check(9999, FAR) is None


def test_under_threshold_not_fuel():
    d = new()
    d.on_level(43, 10, HOME, 1000)
    d.on_level(44, 20, HOME, 1000)  # +4 %
    assert d.check(500, FAR) is None
    assert d.pending is not None and not d.pending.valid


def test_noise_cancelled_when_level_drops():
    d = new()
    assert d.on_level(42, 10, HOME, 1000) == "started"
    assert d.on_level(40, 20, HOME, 1000) == "cancelled"
    assert d.pending is None


def test_settle_time_required_even_when_far():
    d = new()
    d.on_level(50, 10, HOME, 1000)
    assert d.pending.valid
    assert d.check(40, FAR) is None  # nur 30 s seit letztem Zuwachs
    assert d.check(71, FAR) is not None


def test_late_increase_extends_same_fill():
    d = new()
    d.on_level(50, 10, HOME, 1000)
    d.on_level(52, 50, HOME, 1000)  # Nachtropfen 40 s später
    assert d.check(100, FAR) is None  # nur 50 s her
    done = d.check(115, FAR)
    assert done["level"] == 52


def test_electric_no_distance():
    d = new(require_distance=False, settle_seconds=600)
    for i in range(1, 11):
        d.on_level(40 + i * 5, i * 300, HOME, 1000)
    assert d.check(10 * 300 + 100, HOME) is None
    assert d.check(10 * 300 + 601, HOME)["level"] == 90


def test_restart_persistence():
    d = new()
    d.on_level(50, 10, HOME, 1000)
    d2 = det.FuelDetector(pending=d.dump())
    assert d2.check(100, FAR)["level"] == 50


def moving(i):
    """Fahrzeug fährt: alle 100 m ein neuer Punkt (ca. 0,0014 Grad Länge je 100 m)."""
    return (51.7300, 6.2900 + i * 0.0014)


def test_regen_is_not_charging():
    """Rekuperation: der Akku steigt beim Fahren in kleinen Schritten, nach 400 m sind es keine 5 % (und es wird nie ein Ladevorgang)."""
    d = det.FuelDetector(settle_seconds=60, require_distance=False, reject_moving=True)
    d.on_level(40, 0, moving(0), 1000)
    events = [d.on_level(40 + i, 10 * i, moving(i), 1000 + i * 0.1) for i in range(1, 16)]
    assert "valid" not in events and not (d.pending and d.pending.valid)
    assert "cancelled" in events


def test_charging_stationary_is_detected():
    d = det.FuelDetector(settle_seconds=60, require_distance=False, reject_moving=True)
    d.on_level(40, 0, HOME, 1000)
    events = [d.on_level(40 + i * 2, 10 + i * 30, (51.7300 + (i % 3) * 0.0001, 6.2900), 1000) for i in range(1, 16)]  # GPS-Rauschen von ca. 10 m
    assert events.count("valid") == 1 and d.pending.level == 70
    assert d.check(10 + 15 * 30 + 100, HOME, 1000) is None   # Auto steht noch am Ladeort: Ladung bleibt offen (Pausen)
    assert d.check(10 + 15 * 30 + 100, FAR, 1000)["level"] == 70


def test_driving_off_after_charging_ignores_regen():
    d = det.FuelDetector(settle_seconds=60, require_distance=False, reject_moving=True)
    d.on_level(40, 0, HOME, 1000)
    for i in range(1, 8):
        d.on_level(40 + i * 5, i * 30, HOME, 1000)   # lädt auf 75 %
    assert d.pending.valid and d.pending.level == 75
    d.on_level(76, 400, FAR, 1001.5)                    # weggefahren, Rekuperation
    d.on_level(77, 420, FAR, 1002)
    assert d.pending.level == 75, "Anstieg nach dem Wegfahren zählt nicht"
    assert d.check(210 + 100, FAR)["level"] == 75


def test_odometer_rule_without_gps():
    d = det.FuelDetector(settle_seconds=60, require_distance=False, reject_moving=True)
    d.on_level(40, 0, None, 1000)
    events = [d.on_level(40 + i, 10 * i, None, 1000 + i * 0.4) for i in range(1, 12)]
    assert "valid" not in events


def test_default_detector_unchanged():
    """Verbrenner: kein Bewegungs-Test (beim Tanken fährt man nicht, aber es ändert sich nichts am Verhalten)."""
    d = new()
    for i in range(1, 8):
        d.on_level(40 + i * 5, i * 30, HOME, 1000)
    assert d.pending.valid


def _charging(**kw):
    d = new(reject_moving=True, require_distance=False, settle_seconds=600, **kw)
    d.on_level(45, 100, HOME, 1000)
    d.on_level(52, 200, HOME, 1000)
    assert d.pending.valid
    return d


def test_ev_long_pause_keeps_charge_open():
    d = _charging()
    assert d.check(200 + 5 * 3600, HOME, 1000) is None            # Stunden Pause (Wolken): nicht beendet
    d.on_level(60, 200 + 6 * 3600, HOME, 1000)                      # Ladung geht weiter, derselbe Vorgang
    assert d.pending.level == 60


def test_ev_ends_when_car_moves_or_unplugged():
    d = _charging()
    assert d.check(2000, FAR, 1000)["level"] == 52                  # weggefahren
    d = _charging()
    assert d.check(2000, HOME, 1000, plugged=True) is None
    assert d.check(2000, HOME, 1000, plugged=False)["level"] == 52  # abgesteckt (Abschlusszeit vorbei)
    d = _charging()
    assert d.check(250, HOME, 1000, plugged=False) is None          # Abschlusszeit noch nicht um (Füllstand meldet verspätet)


def test_ev_without_signals_uses_settle_time():
    d = _charging()
    assert d.check(2000, None, None) ["level"] == 52                # weder Position noch Stecker: wie bisher


def test_ev_hold_has_cap():
    d = _charging()
    assert d.check(200 + det.MAX_HOLD_S + 1, HOME, 1000) is not None


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)


def test_finish_now():
    d = new()
    assert d.finish_now() is None   # noch kein Vorgang: nichts
    for i in range(1, 25):
        d.on_level(40 + i * 2, 10 + i * 5, HOME, 1000)
    assert d.pending and d.pending.valid
    done = d.finish_now()
    assert done and done["level"] == 88 and d.pending is None
    assert d.finish_now() is None
