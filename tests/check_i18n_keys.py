"""Prüft, ob jeder Text, der im Panel (this.T("…")) und im Server-Code (self.tr("…")) benutzt wird, einen Eintrag in en.json hat
und in allen Sprachdateien vorhanden ist. Aufruf: python tests/check_i18n_keys.py"""
import json
import pathlib
import re
import sys

pk = pathlib.Path(__file__).parent.parent / "custom_components" / "drive_energy_doc"
i18n = pk / "frontend" / "i18n"
en = json.loads((i18n / "en.json").read_text(encoding="utf-8"))
js = (pk / "frontend" / "drive-energy-doc-panel.js").read_text(encoding="utf-8")
keys = set(re.findall(r'\bT\("((?:[^"\\]|\\.)*)"', js))
for f in ("vehicle.py", "__init__.py", "receipt.py", "stats.py", "channels.py", "detector.py"):
    keys |= set(re.findall(r'\.tr\("((?:[^"\\]|\\.)*)"', (pk / f).read_text(encoding="utf-8")))
keys = {k.replace('\\"', '"') for k in keys}
miss = sorted(k for k in keys if k not in en)
print(len(keys), "Texte im Code,", len(miss), "ohne Eintrag in en.json")
for k in miss:
    print(" -", k[:120])
gaps = 0
for f in sorted(i18n.glob("*.json")):
    d = json.loads(f.read_text(encoding="utf-8"))
    gaps += sum(1 for k in en if k not in d)
print("Lücken in den Sprachdateien (gegenüber en.json):", gaps)
sys.exit(1 if miss or gaps else 0)
