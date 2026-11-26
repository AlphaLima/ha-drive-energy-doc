"""Ladekurve: python tests/test_curve.py"""
import importlib.util
import pathlib
import sys
import tempfile

base = pathlib.Path(__file__).parent.parent
spec = importlib.util.spec_from_file_location("curve", base / "custom_components" / "drive_energy_doc" / "curve.py")
cv = importlib.util.module_from_spec(spec)
sys.modules["curve"] = cv
spec.loader.exec_module(cv)


def test_add_step_and_round():
    pts = []
    assert cv.add(pts, 1000, 7012.4, None, 41.26)
    assert not cv.add(pts, 1030, 7000, None, 41)      # zu früh
    assert cv.add(pts, 1060, 0, 6900.7, None)
    assert pts == [[1000, 7012, None, 41.3], [1060, 0, 6901, None]]


def test_thinning_keeps_ends():
    pts = []
    for i in range(cv.MAX_POINTS + 1):
        cv.add(pts, i * 60, 1000, None, 50)
    assert len(pts) <= cv.MAX_POINTS and pts[0][0] == 0 and pts[-1][0] == cv.MAX_POINTS * 60


def test_write_read_restore():
    pts = [[1000, 7000, None, 40.0], [1060, 7100, 6900, 41.0]]
    with tempfile.TemporaryDirectory() as d:
        p = pathlib.Path(d) / "curves" / "x.json"
        cv.write(p, pts)
        data = cv.read(p)
        assert data["t0"] == 1000 and data["p"][1][0] == 60
        assert cv.restore(data) == pts
    assert cv.read(pathlib.Path("/nonexistent/x.json")) is None and cv.restore(None) == []


def test_idle_skip_and_trim():
    pts = [[0, 7000, None, 40.0], [60, 7000, None, 41.0], [120, 0, None, 41.0]]
    assert cv.skip_idle(pts, 180, 0, None, 41.0)          # Pause: zu früh
    assert not cv.skip_idle(pts, 120 + 900, 0, None, 41.0)
    assert not cv.skip_idle(pts, 180, 0, None, 42.0)      # Ladestand geändert
    pts += [[1100, 0, None, 41.0], [2000, 0, None, 41.0]]
    assert cv.trim(pts) == pts[:3]


for name in [n for n in dir() if n.startswith("test_")]:
    globals()[name]()
    print("ok", name)
