"""Trockenlauf der Plug-in-Hybrid-Logik in vehicle.py (ohne Home Assistant): Zuordnung von Tank- und Ladebelegen. Aufruf: python tests/sim_phev.py"""
import ast, importlib, pathlib, sys, time, types
from datetime import datetime

root = pathlib.Path(__file__).parent.parent
pkg_dir = root / "custom_components" / "drive_energy_doc"
pkg = types.ModuleType("drive_energy_doc"); pkg.__path__ = [str(pkg_dir)]; sys.modules["drive_energy_doc"] = pkg
importlib.import_module("drive_energy_doc.messages").preload()
stats = importlib.import_module("drive_energy_doc.stats")

src = ast.parse((pkg_dir / "vehicle.py").read_text(encoding="utf-8"))
cls = next(n for n in src.body if isinstance(n, ast.ClassDef) and n.name == "Vehicle")
fns = {n.name: n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
charge = importlib.import_module("drive_energy_doc.charge")
ns = {"charge": charge, "receipt": types.SimpleNamespace(FUEL_GRADES=("diesel", "diesel_premium", "e10", "e5", "ron95", "ron98", "lpg")), "stats": stats, "time": time, "datetime": datetime, "dt_util": types.SimpleNamespace(as_local=lambda x: x, utc_from_timestamp=lambda t: datetime.fromtimestamp(t))}
for name in ("_energy_of", "_fits_energy", "_entry_on", "_newest_within", "_apply_values", "unit_of"):
    node = fns[name]
    node.decorator_list = []
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), "v", "exec"), ns)


class V:
    def __init__(self, phev):
        self.phev, self.unit, self.data = phev, "l", {"entries": []}
    _energy_of = ns["_energy_of"]; _entry_on = ns["_entry_on"]; _newest_within = ns["_newest_within"]; _apply_values = ns["_apply_values"]; unit_of = ns["unit_of"]
    _fits_energy = staticmethod(ns["_fits_energy"])
    def currency_note(self, o): return ""


now = time.time()
fuel = {"id": "f", "ts": now - 3600, "receipt": True, "quantity": 40.0, "kind": None, "photos": [], "note": ""}
ev = {"id": "e", "ts": now - 1800, "receipt": True, "quantity": 12.0, "energy": "electric", "photos": [], "note": ""}
empty = {"id": "t", "ts": now - 600, "receipt": False, "quantity": None, "photos": [], "note": ""}   # nur Tacho-Foto
d = datetime.fromtimestamp(now).date()

v = V(True)
v.data["entries"] = [fuel, ev]
assert v._energy_of({"category": "charging"}) == "electric" and v._energy_of({"category": "fuel"}) == "fuel" and v._energy_of({}) == "fuel"
assert v._entry_on(d, False, "electric")["id"] == "e", "Ladebeleg gehört zum Ladeeintrag"
assert v._entry_on(d, False, "fuel")["id"] == "f", "Tankbeleg gehört zum Tankeintrag"
v.data["entries"] = [fuel, ev, empty]
assert v._entry_on(d, False, "electric")["id"] == "t", "leerer Tacho-Eintrag passt zu beiden"
assert V(False)._energy_of({"category": "charging"}) is None, "andere Fahrzeuge: keine Unterscheidung"
plain = V(False); plain.data = v.data
assert plain._entry_on(d, False, None)["id"] == "t"
# Werte übernehmen: Laden markiert den Eintrag als Strom, Tanken entfernt die Markierung
e1 = {"photos": [], "note": "", "id": "n"}
v._apply_values(e1, {"quantity": 20.0, "total": 8.0, "category": "charging"}, None)
assert e1["energy"] == "electric" and v.unit_of(e1) == "kWh"
v._apply_values(e1, {"quantity": 20.0, "total": 40.0, "category": "fuel"}, None)
assert "energy" not in e1 and v.unit_of(e1) == "l"
e2 = {"photos": [], "note": "", "id": "m"}
V(False)._apply_values(e2, {"quantity": 20.0, "total": 8.0, "category": "charging"}, None)
assert "energy" not in e2, "ohne Plug-in-Hybrid wird nichts umgestellt"
print("OK: Plug-in-Hybrid-Zuordnung")


# ---- automatische Ladeerkennung (zweiter Sensor): Zustandsänderung -> Erkennung -> Abschluss ----
import asyncio
detmod = importlib.import_module("drive_energy_doc.detector")
FuelDetector = detmod.FuelDetector
ns2 = {"stats": stats, "time": time, "datetime": datetime, "uuid": __import__("uuid"), "asyncio": asyncio, "FuelDetector": FuelDetector, "CONF_LEVEL_EL": "lvl_el", "CONF_ODOMETER": "odo", "CONF_TRACKER": "trk", "CONF_POWER": "pwr", "CONF_WB_ENERGY": "wbe", "CONF_WB_POWER": "wbp", "CONF_PLUG": "plug", "CONF_WB_PRICE": "wbpr", "wallbox": __import__("wallbox") if False else None, "CONF_CHARGE_TYPE": "ctype", "CONF_LEVEL": "lvl", "charge": charge, "DOMAIN": "drive_energy_doc",
       "callback": lambda f: f, "Event": object, "dt_util": ns["dt_util"]}
for name in ("_state_changed", "_tick", "_detectors", "_pending_for", "_valid_pending", "_finish"):
    node = fns[name]
    node.decorator_list = []
    node.returns = None
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), "v2", "exec"), ns2)


class Bus:
    def __init__(self): self.fired = []
    def async_fire(self, name, data): self.fired.append((name, data))


class Hass2:
    def __init__(self): self.tasks, self.bus = [], Bus()
    def async_create_task(self, c): self.tasks.append(c)


class V2:
    def __init__(self):
        self.phev, self.electric, self.unit, self.capacity, self.capacity_el = True, False, "l", 50.0, 12.0
        self.o = {"lvl_el": "sensor.akku", "odo": "sensor.km"}
        self.hass, self.name = Hass2(), "Test-PHEV"
        self.data = {"entries": [], "pending": None, "pending_el": None}
        self.detector = FuelDetector(min_increase=5, settle_seconds=60, require_distance=True)
        self.detector_el = FuelDetector(min_increase=5, settle_seconds=60, require_distance=False)
        self._pos = (51.0, 6.0)
        self.said = []
    def _read_float(self, x): return 50000.0 if x == "sensor.km" else None
    def _read_odo(self): return self._read_float("sensor.km")
    def _read_pos(self): return self._pos
    def _save(self): pass
    def _notify_entities(self): pass
    def _apply_values(self, *a): pass
    def _summary(self, e, h): return h
    def tr(self, k, *a): return k
    async def _say(self, m, quick=False, phase=None, el=False): self.said.append(m)
    def _detected_text(self, entry): return "detected"
    def _sample_charge(self): pass
    def _wb_sample(self): pass
    def _plugged(self): return None
    def _curve_sample(self): pass
    _curve = []
    _wb_run = None
    def _charge_det(self): return self.detector_el
    def _ac_max(self): return None
    def _push_at_start(self, det): return True
    async def _push_started(self, det): pass   # früher Push: hier nicht Gegenstand des Tests
    async def _fetch_price(self, pending=None, det=None):
        return {"unit_price": 0.30, "price_source": "eingestellt"} if det is self.detector_el else {"unit_price": 1.80, "price_source": "tankerkoenig"}
    for n in ("_state_changed", "_tick", "_detectors", "_pending_for", "_valid_pending", "_finish"):
        locals()[n] = ns2[n]


class Ev:
    def __init__(self, ent): self.data = {"entity_id": ent}


v2 = V2()
v2._read_float = lambda x: {"sensor.km": 50000.0, "sensor.akku": 40.0, "sensor.tank": 50.0}.get(x)
v2.detector_el.prev_level = 40.0
v2.detector.prev_level = 50.0
v2._read_float = lambda x: 70.0 if x == "sensor.akku" else (50000.0 if x == "sensor.km" else None)
v2._state_changed(Ev("sensor.akku"))
assert v2.detector_el.pending and v2.detector_el.pending.valid and v2.detector.pending is None, "Laden erkannt, Tank unberührt"
assert v2._valid_pending() is v2.detector_el.pending and v2._pending_for("electric") is v2.detector_el.pending
assert v2.hass.tasks, "Strompreis wird geholt"
for c in v2.hass.tasks: asyncio.run(c)
v2.hass.tasks.clear()
v2.detector_el.pending.last_increase_ts -= 1000   # lange nichts mehr gestiegen: Vorgang ist fertig
v2._tick(None)
for c in v2.hass.tasks: asyncio.run(c)
assert len(v2.data["entries"]) == 1, v2.data["entries"]
e_el = v2.data["entries"][0]
assert e_el["est_quantity"] == 3.6 and e_el["quantity"] == 3.6 and e_el["quantity_source"] == "berechnet", e_el   # Schätzung bleibt am Eintrag, ohne Belege kein Korrekturfaktor
assert "charge_type" not in e_el   # kein Leistungssensor und zu kurz für eine mittlere Leistung
en_ = v2.data["entries"][0]
assert en_["energy"] == "electric"
assert abs(en_["quantity"] - (70 - 40) / 100 * 12.0) < 1e-6 and en_["unit_price"] == 0.30 and abs(en_["total"] - 3.6 * 0.30) < 0.01, en_
assert v2.data["pending_el"] is None and v2.detector_el.pending is None
# Tankvorgang parallel: Tank-Sensor steigt, Akku bleibt
v2._read_float = lambda x: 90.0 if x == "sensor.tank" else None
v2.o["lvl"] = "sensor.tank"
v2.detector.prev_level = 40.0
v2._state_changed(Ev("sensor.tank"))
assert v2.detector.pending and v2.detector.pending.valid and v2.detector_el.pending is None
print("OK: Ladeerkennung (zweiter Sensor) und Abschluss")
