"""Trockenlauf von Neuimport, Foto-Migration und Neu-Einlesen an einer Kopie der echten Daten (ohne Home Assistant, KI wird nachgestellt).
Aufruf: python tests/sim_reimport.py <Config-Ordner mit drive_energy_doc/ und .storage/> <Entry-ID>"""
import ast, asyncio, importlib, json, logging, pathlib, shutil, sys, tempfile, textwrap, types
from datetime import date, datetime

root = pathlib.Path(__file__).parent.parent
pkg_dir = root / "custom_components" / "drive_energy_doc"
pkg = types.ModuleType("drive_energy_doc"); pkg.__path__ = [str(pkg_dir)]; sys.modules["drive_energy_doc"] = pkg
importlib.import_module("drive_energy_doc.messages").preload()
receipt = importlib.import_module("drive_energy_doc.receipt")
stats = importlib.import_module("drive_energy_doc.stats")

cfg_src, eid = pathlib.Path(sys.argv[1]), sys.argv[2]
tmp = pathlib.Path(tempfile.mkdtemp())
shutil.copytree(cfg_src / "drive_energy_doc", tmp / "drive_energy_doc")
store = json.loads((cfg_src / ".storage" / f"drive_energy_doc.{eid}").read_text(encoding="utf-8"))["data"]

src = ast.parse((pkg_dir / "vehicle.py").read_text(encoding="utf-8"))
cls = next(n for n in src.body if isinstance(n, ast.ClassDef) and n.name == "Vehicle")
fns = {n.name: n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
ns = {"Path": pathlib.Path, "datetime": datetime, "receipt": receipt, "stats": stats, "dt_util": types.SimpleNamespace(
    as_local=lambda x: x, utc_from_timestamp=lambda t: datetime.fromtimestamp(t)), "DOMAIN": "drive_energy_doc", "_LOGGER": logging.getLogger("sim"), "asyncio": asyncio}
for name in ("_rescan_marker", "_import_folder", "_migrate_photos", "rescan_photos"):
    mod = ast.Module(body=[fns[name]], type_ignores=[])
    exec(compile(ast.fix_missing_locations(mod), "vehicle_part", "exec"), ns)


class Hass:
    class config:
        @staticmethod
        def path(*p): return str(tmp.joinpath(*p))
    async def async_add_executor_job(self, f, *a): return f(*a)


class V:
    name = "BMW X1"
    media_dir = tmp
    def __init__(self):
        self.hass = Hass()
        self.data = {"entries": store["entries"]}
        self.photo_dir = tmp / "drive_energy_doc" / eid / "photos"
        self.orig_dir = tmp / "drive_energy_doc" / eid / "originals"
        self._upload_lock = asyncio.Lock()
    def _ai_entity(self): return "ai_task.fake"
    def _km_sane(self, *a, **k): return True
    def _save(self): pass
    def _notify_entities(self): pass
    _rescan_marker = ns["_rescan_marker"]; _import_folder = ns["_import_folder"]; _migrate_photos = ns["_migrate_photos"]; rescan_photos = ns["rescan_photos"]


v = V()
imp = tmp / "drive_energy_doc" / "import"
shutil.copytree(imp / "BMW X1.done", imp / "BMW X1")
(imp / "BMW X1" / "REPLACE").write_text("")
(tmp / "drive_energy_doc" / "rescan").mkdir()
(tmp / "drive_energy_doc" / "rescan" / "BMW X1").write_text("")
before = len(v.data["entries"])
v._import_folder()
print("Einträge nach Import:", len(v.data["entries"]), "(vorher", before, ")")
v._migrate_photos()
names = [n for e in v.data["entries"] for n in e.get("photos", [])]
print("Fotos:", len(names), "Beispiele:", names[:3])
assert all(not n[0:10].isdigit() or n[4] == "-" for n in names), "alter Name übrig"
print("Backup:", [p.name for p in (tmp / "drive_energy_doc" / "backup").iterdir()])
orphans = [f.name for f in v.photo_dir.glob("*.jpg") if f.name not in names]
print("verwaiste Dateien in photos/:", orphans)


async def fake_ai(hass, entity, image, media):   # nachgestellte KI: liest nur Menge/Datum, sonst nichts
    return {"quantity": 50.0, "unit_price": 1.9, "total": 95.0, "odometer": None, "date": date(2026, 10, 1), "time": (9, 30), "currency": "EUR", "category": "fuel", "item": None, "station": "Teststation", "address": None, "crop": [50, 50, 950, 950]}
receipt.ai_read = fake_ai
asyncio.run(v.rescan_photos())
names2 = [n for e in v.data["entries"] for n in e.get("photos", [])]
print("nach Neu-Einlesen:", names2[:3])
files = sorted(f.name for f in v.photo_dir.glob("*.jpg"))
assert sorted(names2) == files, (len(names2), len(files))
assert sorted(f.name for f in v.orig_dir.glob("*.jpg")) == files
assert not (tmp / "drive_energy_doc" / "rescan" / "BMW X1").exists()
print("Bericht:", [p.name for p in (tmp / "drive_energy_doc").glob("rescan_*.csv")])
print((next((tmp / "drive_energy_doc").glob("rescan_*.csv"))).read_text(encoding="utf-8-sig").splitlines()[:4])
print("OK, Testordner:", tmp)
