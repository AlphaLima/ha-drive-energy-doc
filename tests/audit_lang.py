import collections
import json
import pathlib

pk = pathlib.Path(__file__).parent.parent / "custom_components" / "drive_energy_doc"
i18n = pk / "frontend" / "i18n"
files = {f.stem: json.loads(f.read_text(encoding="utf-8")) for f in sorted(i18n.glob("*.json"))}
en = files["en"]
print("Sprachdateien:", len(files), sorted(files))
print("Schlüssel in en:", len(en), "| davon kw.*:", [k for k in en if k.startswith("kw.")])
# 1) Schlüssel, bei denen eine Sprache den deutschen Schlüsseltext oder den englischen Text unverändert hat
sus = collections.defaultdict(list)
for l, d in files.items():
    if l == "en":
        continue
    for k, v in d.items():
        if k.startswith("kw."):
            continue
        if v == k and len(k) > 4:
            sus[l].append(("=deutsch", k))
        elif v == en.get(k) and len(k) > 6 and v != k:
            sus[l].append(("=englisch", k))
print("\nauffällig (Wert = deutscher Schlüssel oder = Englisch), Anzahl je Sprache:")
for l in sorted(sus):
    print(" ", l, len(sus[l]), [x[1][:28] for x in sus[l][:4]])
# 2) Übersetzungs-Dateien der Konfiguration, services.yaml
tr = sorted(p.name for p in (pk / "translations").glob("*.json"))
print("\ntranslations/:", tr)
print("Panel-Titel (messages.py) Sprachen:")
src = (pk / "messages.py").read_text(encoding="utf-8")
print("  PANEL_TITLES vorhanden:", "panel_title" in src)
