"""Trockenlauf: Tacho-Foto zuerst, danach die Säule/der Beleg (reiner Foto-Betrieb). Aufruf: python tests/sim_odo.py"""
import asyncio, ast, importlib, pathlib, sys, time, types
from datetime import datetime

root = pathlib.Path(__file__).parent.parent
pkg_dir = root / "custom_components" / "drive_energy_doc"
pkg = types.ModuleType("drive_energy_doc"); pkg.__path__ = [str(pkg_dir)]; sys.modules["drive_energy_doc"] = pkg
importlib.import_module("drive_energy_doc.messages").preload()
stats = importlib.import_module("drive_energy_doc.stats")
src = ast.parse((pkg_dir / "vehicle.py").read_text(encoding="utf-8"))
cls = next(n for n in src.body if isinstance(n, ast.ClassDef) and n.name == "Vehicle")
fns = {n.name: n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
ns = {"stats": stats, "time": time, "uuid": __import__("uuid"), "CONF_LEVEL": "lvl", "CONF_ODOMETER": "odo", "OPEN_WINDOW": 6 * 3600,
      "dt_util": types.SimpleNamespace(as_local=lambda x: x, utc_from_timestamp=lambda t: datetime.fromtimestamp(t))}
for name in ("_odometer", "_open_entry", "_fits_energy", "_new_manual_entry", "_retime"):
    node = fns[name]
    node.decorator_list = []
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), "v", "exec"), ns)


class V:
    def __init__(self):
        self.o, self.data, self.said, self.applied = {}, {"entries": []}, [], []   # kein Füllstandssensor = reiner Foto-Betrieb
        self._pos = None
    def _valid_pending(self): return None
    def _check_cons(self, entries, entry, km): return None
    def _read_float(self, x): return None
    def _fmt_km(self, k): return f"{k:.0f}"
    def _save(self): pass
    def _notify_entities(self): pass
    def _remind_receipt(self, e): pass
    def tr(self, k, *a): return k
    async def _say(self, m): self.said.append(m)
    async def _apply_odometer(self, e, km, photo, dt): self.applied.append((e["id"], km)); e["odometer"], e["odometer_source"] = km, "foto"
    async def _skip_km(self, e, km, photo, why): self.said.append("Zusatzfoto gespeichert.")
    for n in ("_odometer", "_open_entry", "_new_manual_entry"):
        locals()[n] = ns[n]
    _retime = staticmethod(ns["_retime"]); _fits_energy = staticmethod(ns["_fits_energy"])


v = V()
now = time.time()
# vorhandener Eintrag mit Beleg und Kilometerstand von einem Foto (vor einer Minute)
prev = {"id": "a", "created": now - 60, "ts": now - 60, "receipt": True, "quantity": 14.2, "odometer": 12118.0, "odometer_source": "foto", "photos": []}
v.data["entries"] = [prev]
asyncio.run(v._odometer(12205.0, "tacho2.jpg"))      # Tacho zum NÄCHSTEN Vorgang (87 km mehr)
assert len(v.data["entries"]) == 2, "neuer Eintrag statt Zusatzfoto am vorigen"
new = next(e for e in v.data["entries"] if e["id"] != "a")
assert new["odometer"] == 12205.0 and v.applied[-1][1] == 12205.0 and "Zusatzfoto" not in " ".join(v.said)
assert prev["photos"] == [] and prev["odometer"] == 12118.0, "der vorige Eintrag bleibt unberührt"
# Der Beleg danach findet den offenen Eintrag (noch ohne Beleg)
assert v._open_entry("receipt") is new
# Ein zweites Tacho-Foto mit fast demselben Stand (z. B. unscharfes Duplikat) legt KEINEN weiteren Eintrag an
v2 = V(); v2.data["entries"] = [dict(prev)]
asyncio.run(v2._odometer(12130.0, "tacho_dup.jpg"))  # nur 12 km mehr: gleicher Vorgang
assert len(v2.data["entries"]) == 1, "geringer Unterschied: kein neuer Eintrag"
print("OK: Tacho zuerst legt einen neuen Eintrag an")


# ---- derselbe Beleg noch einmal: Rückfrage statt zweitem Eintrag ----
import datetime as _dt
node = fns["_duplicate_of"]; node.decorator_list = []
exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), "v3", "exec"), ns)
class V3(V):
    _duplicate_of = ns["_duplicate_of"]
v3 = V3()
base = {"id": "x", "kind": None, "receipt": True, "quantity": 14.2, "total": 6.96, "ts": now - 600, "created": now - 600}
v3.data["entries"] = [base]
same = {"quantity": 14.2, "total": 6.96, "unit_price": 0.49}
assert v3._duplicate_of(same, None)["id"] == "x", "gleiche Menge und gleicher Betrag ohne Datum: Duplikat"
assert v3._duplicate_of({**same, "date": _dt.datetime.fromtimestamp(now - 600).date()}, None)["id"] == "x", "gleiches Datum: Duplikat"
assert v3._duplicate_of({**same, "date": _dt.date(2020, 1, 1)}, None)["id"] == "x", "gerade erst angelegt (Datum war nur der Upload): trotz anderem Datum derselbe Beleg"
base["created"] = now - 8 * 3600
assert v3._duplicate_of({**same, "date": _dt.date(2020, 1, 1)}, None) is None, "älterer Eintrag mit anderem Datum: kein Duplikat"
base["created"] = now - 600
assert v3._duplicate_of({"quantity": 14.2, "total": 7.50}, None) is None, "anderer Betrag: kein Duplikat"
assert v3._duplicate_of({"quantity": 11.8, "total": 6.14}, None) is None, "andere Menge: kein Duplikat"
base["ts"] = base["created"] = now - 5 * 86400
assert v3._duplicate_of(same, None) is None, "älter als drei Tage und ohne Datum: kein Duplikat"
base.update(ts=now - 600, created=now - 600, kind="extra")
assert v3._duplicate_of(same, None) is None, "Zubehör zählt nicht"
base.update(kind=None, energy="electric")
assert v3._duplicate_of(same, "fuel") is None and v3._duplicate_of(same, "electric")["id"] == "x", "Plug-in-Hybrid: Energieart muss passen"
print("OK: Duplikat-Erkennung")


# ---- Zubehör bekommt den zuletzt bekannten Kilometerstand; ein Tacho-Foto danach ersetzt ihn ----
for name in ("_last_known_km", "_stamp_km"):
    node = fns[name]; node.decorator_list = []
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), "v4", "exec"), ns)
class V4(V):
    _last_known_km = ns["_last_known_km"]; _stamp_km = ns["_stamp_km"]
v4 = V4()
fuel_e = {"id": "f", "ts": now - 7200, "created": now - 7200, "receipt": True, "quantity": 40.0, "odometer": 12118.0, "odometer_source": "foto", "photos": []}
v4.data["entries"] = [fuel_e]
ex = {"id": "x", "kind": "extra", "ts": now - 30, "created": now - 30, "odometer": None, "photos": []}
v4._stamp_km(ex)
assert ex["odometer"] == 12118.0 and ex["odometer_source"] == "bekannt", ex
older = {"id": "y", "kind": "extra", "ts": now - 9000, "odometer": None}
v4._stamp_km(older)
assert older["odometer"] is None, "vor dem ersten bekannten Stand: nichts schätzen"
v4.data["entries"].append(ex)
asyncio.run(v4._odometer(12150.0, "tacho_ex.jpg"))    # Tacho-Foto direkt nach dem Zubehör-Beleg
assert v4.applied and v4.applied[-1] == ("x", 12150.0), v4.applied
print("OK: Zubehör bekommt den bekannten Kilometerstand, der Tacho ersetzt ihn")


# ---- Warnung quittieren: ausgeblendet, solange der Hinweis gleich bleibt; ändert sich der Wert, erscheint sie wieder ----
import json as _json
ns["json"] = _json
for name in ("entries_with_stats", "_warn_sig", "ack_warning", "get_entry"):
    node = fns[name]; node.decorator_list = []
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), "v5", "exec"), ns)
class V5(V):
    capacity, capacity_el, phev, electric = 50.0, 0.0, False, False
    entries_with_stats = ns["entries_with_stats"]; ack_warning = ns["ack_warning"]; get_entry = ns["get_entry"]
    _warn_sig = staticmethod(ns["_warn_sig"])
v5 = V5()
ea = {"id": "a", "ts": 1.0, "quantity": 21.6, "unit_price": 1.789, "total": 38.64, "odometer": 100.0, "receipt": True, "photos": []}
eb = {"id": "b", "ts": 2.0, "quantity": 21.6, "unit_price": 1.789, "total": 38.64, "odometer": 600.0, "receipt": True, "photos": []}
v5.data["entries"] = [ea, eb]
w = {e["id"]: e["warn"] for e in v5.entries_with_stats()}
assert w["b"]["total"]["k"] == "dup" and w["a"]["qty"]["k"] == "dup", w
assert v5.ack_warning("b", "total") is True
w = {e["id"]: e["warn"] for e in v5.entries_with_stats()}
assert w["b"] == {} and "qty" in w["a"], "b quittiert (Menge, Preis, Betrag zusammen), a weiter markiert"
assert v5.ack_warning("b", "total") is True and v5.ack_warning("nix", "total") is False, "wiederholtes Quittieren schadet nicht, unbekannter Eintrag: False"
eb["total"] = 40.0                                                              # Wert geändert: anderer Hinweis, die Quittung gilt nicht mehr
w = {e["id"]: e["warn"] for e in v5.entries_with_stats()}
assert "total" in w["b"] and w["b"]["total"]["k"] == "calc", w["b"]
print("OK: Warnung quittieren")


# ---- Display und Beleg desselben Vorgangs (gleicher Preis, Menge/Betrag vom Display falsch gelesen) ----
node = fns["_same_event"]; node.decorator_list = []
exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), "v6", "exec"), ns)
class V6(V):
    _same_event = ns["_same_event"]; _fits_energy = staticmethod(ns["_fits_energy"])
v6 = V6()
disp = {"id": "d", "created": now - 300, "ts": now - 300, "receipt": True, "quantity": 37.9, "unit_price": 1.769, "total": 67.07, "station": None}
v6.data["entries"] = [disp]
beleg = {"quantity": 17.9, "unit_price": 1.769, "total": 31.67, "station": "Landstrom Tankstelle"}
e_, mode = v6._same_event(beleg, None)
assert e_["id"] == "d" and mode == "receipt", "Beleg gehört zum Display-Eintrag"
assert v6._same_event({"quantity": 5.0, "unit_price": 2.0, "total": 10.0, "station": "X"}, None) is None, "anderer Preis: anderer Vorgang"
assert v6._same_event({"quantity": 17.9, "unit_price": 1.769, "total": 31.67}, None) is None, "Display zu Display: Sache der Duplikat-Erkennung"
disp["station"] = "Landstrom"; disp["created"] = now - 100
e2, mode2 = v6._same_event({"quantity": 37.9, "unit_price": 1.769, "total": 67.07}, None)
assert e2["id"] == "d" and mode2 == "display", "Display-Foto zu einem vorhandenen Beleg-Eintrag"
disp["created"] = now - 8 * 3600
assert v6._same_event(beleg, None) is None and v6._same_event({"unit_price": 1.769}, None) is None, "älter als 6 Stunden: nicht zuordnen"
print("OK: Display und Beleg desselben Vorgangs")

