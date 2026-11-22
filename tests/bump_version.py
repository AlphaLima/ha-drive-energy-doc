"""Version in manifest.json und im Panel erhöhen (liest vollständig, bevor geschrieben wird).

python tests/bump_version.py            -> nächste Patch-Version
python tests/bump_version.py 0.1.33     -> feste Version (auch zum Reparieren)
"""

import json
import pathlib
import re
import sys

base = pathlib.Path(__file__).parent.parent / "custom_components" / "drive_energy_doc"
manifest_path = base / "manifest.json"
panel_path = base / "frontend" / "drive-energy-doc-panel.js"

DEFAULT = {
    "domain": "drive_energy_doc",
    "name": "Drive Energy Doc",
    "after_dependencies": ["ai_task"],
    "categories": ["vehicles_transport.cars_evs", "energy.ev_charging"],
    "codeowners": ["@AlphaLima"],
    "config_flow": True,
    "dependencies": ["http", "websocket_api", "frontend", "panel_custom", "file_upload"],
    "documentation": "https://github.com/AlphaLima/ha-drive-energy-doc",
    "integration_type": "service",
    "iot_class": "cloud_polling",
    "issue_tracker": "https://github.com/AlphaLima/ha-drive-energy-doc/issues",
    "requirements": [],
    "version": "0.1.0",
}

text = manifest_path.read_text(encoding="utf-8")
try:
    manifest = json.loads(text)
except ValueError:
    manifest = dict(DEFAULT)  # Datei leer oder kaputt: Grundgerüst wiederherstellen

if len(sys.argv) > 1:
    new = sys.argv[1]
else:
    major, minor, patch = manifest["version"].split(".")
    new = f"{major}.{minor}.{int(patch) + 1}"
manifest["version"] = new

out = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
assert out.strip().startswith("{") and '"domain": "drive_energy_doc"' in out
manifest_path.write_text(out, encoding="utf-8")

panel = panel_path.read_text(encoding="utf-8")
panel2 = re.sub(r'const VERSION = "[^"]+";', f'const VERSION = "{new}";', panel, count=1)
assert panel2.count("const VERSION") == 1
panel_path.write_text(panel2, encoding="utf-8")
print("Version", new)
