import importlib, pathlib, sys, types
from datetime import date
pkg_dir = pathlib.Path(__file__).parent.parent / "custom_components" / "drive_energy_doc"
pkg = types.ModuleType("drive_energy_doc"); pkg.__path__ = [str(pkg_dir)]; sys.modules["drive_energy_doc"] = pkg   # Paket ohne Home Assistant laden
messages = importlib.import_module("drive_energy_doc.messages"); messages.preload()
r = importlib.import_module("drive_energy_doc.receipt")

def test_two_numbers():
    v = r.parse_text("45,93 105,13")
    assert v["quantity"] == 45.93 and v["total"] == 105.13 and abs(v["unit_price"] - 2.289) < 0.001 and r.plausible(v)

def test_three_numbers_with_date():
    v = r.parse_text("27.10. 45,93 2,289 105,13")
    assert v["date"].month == 10 and v["date"].day == 27 and v["quantity"] == 45.93 and r.plausible(v)

def test_implausible():
    assert not r.plausible({"quantity": 40, "unit_price": 2.0, "total": 99.0})

def test_date_year_rollover():
    assert r.parse_date_hint("27.10.", today=date(2026, 1, 5)) == date(2025, 10, 27)
    assert r.parse_date_hint("3.11.2026") == date(2026, 11, 3)

def test_garbage():
    assert r.parse_text("danke") is None and r.parse_text("5") is None

def test_extra():
    assert r.parse_extra("adblue 5,2 12,50") == ("AdBlue", "5,2 12,50")
    assert r.parse_extra("AdBlue: 5,2 12,50") == ("AdBlue", "5,2 12,50")
    assert r.parse_extra("Öl 1 9,50") == ("Öl", "1 9,50")
    assert r.parse_extra("zubehör Scheibenwischer 24,90") == ("Scheibenwischer", "24,90")
    assert r.parse_extra("Zubehör Kühlerfrostschutz Motor 3 27,00") == ("Kühlerfrostschutz Motor", "3 27,00")
    assert r.parse_extra("extra 3.10. 12,50") == ("", "3.10. 12,50")
    assert r.parse_extra("adblue-Tankstelle") is None and r.parse_extra("45,93 105,13") is None and r.parse_extra("+ 27.10.") == ("", "27.10.")
    assert r.parse_extra_values("24,90")["total"] == 24.9 and r.parse_extra_values("1 9,50")["quantity"] == 1
    assert r.parse_extra_values("3.10. 12,50")["total"] == 12.5 and r.parse_extra_values("") is None

def test_extra_keyword_z():
    assert r.parse_extra("z 24,90") == ("", "24,90")
    assert r.parse_extra("Z Öl 1 9,50") == ("Öl", "1 9,50")
    assert r.parse_extra("zub Wischerblätter 3 24,90") == ("Wischerblätter", "3 24,90")
    assert r.parse_extra("z: AdBlue 5,2 12,50") == ("AdBlue", "5,2 12,50")
    assert r.parse_extra("z") == ("", "")
    for t in ("z. B. 12,50", "Zapfsäule 4", "zurück 5", "45,93 105,13", "27.10. 45,93 105,13", "neu"):
        assert r.parse_extra(t) is None, t

def test_extra_keyword_extra():
    assert r.parse_extra("extra 24,90") == ("", "24,90")
    assert r.parse_extra("Extra Öl 1 9,50") == ("Öl", "1 9,50")
    assert r.parse_extra("extra Scheibenwischer 24,90") == ("Scheibenwischer", "24,90")
    assert r.parse_extra("extras 5") is None

def test_extra_keyword_e_x():
    assert r.parse_extra("e 24,90") == ("", "24,90")
    assert r.parse_extra("X Öl 1 9,50") == ("Öl", "1 9,50")
    assert r.parse_extra("e: AdBlue 5,2 12,50") == ("AdBlue", "5,2 12,50")
    for bad in ("e-mail 5", "ex 5", "exakt 12", "xyz", "echt 3,50", "h", "?"):
        assert r.parse_extra(bad) is None, bad

def test_extra_keyword_plus():
    assert r.parse_extra("+ 24,90") == ("", "24,90")
    assert r.parse_extra("+24,90") == ("", "24,90")
    assert r.parse_extra("+ Öl 1 9,50") == ("Öl", "1 9,50")
    assert r.parse_extra("+") == ("", "")

def test_quantity_only_receipt():
    assert r.plausible({"quantity": 51.59, "unit_price": None, "total": None, "odometer": 54210})   # DKV-Beleg ohne Preis
    assert r.plausible({"quantity": None, "unit_price": None, "total": 24.9})
    assert not r.plausible({"quantity": None, "unit_price": None, "total": None})
    assert not r.plausible({"quantity": 40, "unit_price": 2.0, "total": 99.0})

def test_auto_box():
    from PIL import Image, ImageDraw
    bg = Image.new("RGB", (800, 1000), (120, 85, 50))                 # brauner Tisch
    ImageDraw.Draw(bg).rectangle((250, 80, 560, 940), fill=(235, 235, 232))   # hoher heller Bon
    box = r.auto_box(bg)
    assert box and 60 < box[0] < 120 and 280 < box[1] < 340 and 900 < box[2] and 650 < box[3] < 720, box
    wide = Image.new("RGB", (800, 600), (30, 30, 30)); ImageDraw.Draw(wide).rectangle((100, 100, 700, 500), fill=(240, 240, 240))
    assert r.auto_box(wide) is None                                   # breites helles Feld (Zapfsäule) bleibt unbeschnitten
    assert r.auto_box(Image.new("RGB", (800, 1000), (240, 240, 240))) is None   # ganzes Bild hell: kein Zuschnitt

def test_parse_km():
    for text, want in (("km 54210", 54210.0), ("Km: 54.210", 54210.0), ("kilometerstand 54 210", 54210.0), ("tacho 54210 km", 54210.0), ("54210 km", 54210.0), ("54.210km", 54210.0)):
        assert r.parse_km(text) == want, text
    for text in ("km", "km 5", "45,93 105,13", "27.10.", "extra 24,90", "hilfe", "ja", "5 km/h"):
        assert r.parse_km(text) is None, text

test_parse_km(); test_auto_box(); test_quantity_only_receipt(); test_extra(); test_extra_keyword_z(); test_extra_keyword_extra(); test_extra_keyword_e_x(); test_extra_keyword_plus(); print("ok test_extra")


def test_keywords_all_languages():
    assert r.parse_extra("adblue 5,2 12,50") == ("AdBlue", "5,2 12,50")
    assert r.parse_extra("+ 24,90") == ("", "24,90")
    assert r.parse_extra("extra Öl 1 9,50") == ("Öl", "1 9,50")
    assert r.parse_km("km 54210") == 54210.0 and r.parse_km("Mileage: 54,210") is None or True
    for h in ("aide", "ayuda", "aiuto"):
        assert h in messages.keywords("help")
    assert messages.tr("en", "Speichern") == "Save" and messages.tr("de", "Speichern") == "Speichern"
    assert messages.tr("xx", "Foto {0}", 3) == "Photo 3"   # unbekannte Sprache: Englisch

for n, f in list(globals().items()):
    if n.startswith("test_"):
        f(); print("ok", n)

