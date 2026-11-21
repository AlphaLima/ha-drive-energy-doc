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


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
