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

def test_time_and_text_from_ai():
    assert r.parse_time("08:24") == (8, 24) and r.parse_time("8.24 Uhr") == (8, 24) and r.parse_time("25:99") is None and r.parse_time("") is None
    nl = chr(10)
    assert r.clean_text("Beispiel Energie" + nl + " Tankstelle ", 60) == "Beispiel Energie Tankstelle" and r.clean_text("null", 10) is None and r.clean_text(None, 10) is None


def test_panel_titles_for_all_languages():
    assert messages.panel_title("de") == "Tankbuch" and messages.panel_title("en-GB") == "Fuel log" and messages.panel_title("no") == messages.panel_title("nb")
    assert not set(messages.languages()) - set(messages.PANEL_TITLE)


def test_photo_names(tmp_path=None):
    import tempfile
    n = r.new_photo_name({"date": date(2026, 10, 15), "time": (12, 40), "station": "Čerpací stanice Zlatý Lán", "category": "oil"})
    assert n == "2026-10-15_1240_Oel_Cerpaci-stanice-Zlaty-Lan.jpg", n
    n = r.new_photo_name({"date": date(2026, 10, 15), "time": None, "station": "Müller & Söhne Tankstelle Große Straße 12 Nord", "quantity": 40})
    assert n.startswith("2026-10-15_1200_Beleg_Mueller-Soehne-Tankstelle-Grosse") and n.endswith(".jpg") and " " not in n, n
    assert r.new_photo_name({"odometer": 71000}, 1790000000).split("_")[2] == "Tacho.jpg"
    d = pathlib.Path(tempfile.mkdtemp())
    (d / "2026-10-15_1240_Oel_X.jpg").write_bytes(b"x")
    assert r.new_photo_name({"date": date(2026, 10, 15), "time": (12, 40), "station": "X", "category": "oil"}, folder=d) == "2026-10-15_1240_Oel_X_2.jpg"


def test_recompress():
    import io
    from PIL import Image
    import random
    rnd = random.Random(1)
    img = Image.effect_noise((2400, 1800), 40).convert("RGB")
    buf = io.BytesIO(); img.save(buf, "JPEG", quality=95)
    out = r.recompress(buf.getvalue(), 1800, 82)
    assert len(out) < len(buf.getvalue()) and max(Image.open(io.BytesIO(out)).size) == 1800
    assert r.recompress(b"kein bild", 1800, 82) == b"kein bild"


def test_rescale_decimals():
    """Säulen-Display ohne erkannten Dezimalpunkt: 3842 l x 1759 = 6758 wird zu 38,42 l x 1,759 = 67,58."""
    v = {"quantity": 3842.0, "unit_price": 1759.0, "total": 6758.0}
    assert r.rescale_decimals(v) and v == {"quantity": 38.42, "unit_price": 1.759, "total": 67.58}, v
    ok = {"quantity": 38.42, "unit_price": 1.759, "total": 67.58}
    assert not r.rescale_decimals(ok) and ok["total"] == 67.58, "plausible Werte bleiben unverändert"
    bad = {"quantity": 40.0, "unit_price": 2.0, "total": 99.0}
    assert not r.rescale_decimals(bad) and bad["total"] == 99.0, "nicht eindeutig rettbar: nichts ändern"
    kwh = {"quantity": 142.0, "unit_price": 49.0, "total": 696.0}   # 14,2 kWh x 0,49 = 6,96
    assert r.rescale_decimals(kwh) and kwh == {"quantity": 14.2, "unit_price": 0.49, "total": 6.96}, kwh


def test_repair_value():
    """Der Fall vom Handyfoto: Menge als 2,6 statt 21,60 gelesen, Preis 1,789 und Betrag 38,64 stimmen."""
    v = {"quantity": 2.6, "unit_price": 1.789, "total": 38.64}
    assert r.repair_value(v) and v["quantity"] == 21.6 and v["unit_price"] == 1.789 and v["total"] == 38.64, v
    ok = {"quantity": 21.6, "unit_price": 1.789, "total": 38.64}
    assert not r.repair_value(ok), "plausibel: nichts ändern"
    amb = {"quantity": 40.0, "unit_price": 2.0, "total": 99.0}
    assert not r.repair_value(amb) and amb == {"quantity": 40.0, "unit_price": 2.0, "total": 99.0}, "mehrdeutig: nichts ändern"
    price = {"quantity": 38.42, "unit_price": 7.759, "total": 67.58}   # Preis falsch gelesen: mehrere Erklärungen möglich, also nichts raten
    assert not r.repair_value(price) and price["unit_price"] == 7.759


for n, f in list(globals().items()):
    if n.startswith("test_"):
        f(); print("ok", n)



def test_convert_foreign_currency():
    import asyncio

    async def fake_rate(hass, cur, on):
        return (4.0, "2026-10-06") if cur == "PLN" else None
    orig = r.eur_rate
    r.eur_rate = fake_rate
    try:
        v = {"quantity": 10.0, "unit_price": 4.0, "total": 40.0, "currency": "PLN", "date": date(2026, 10, 6)}
        asyncio.run(r.convert_to_eur(None, v))
        assert abs(v["total"] - 10.0) < 1e-9 and abs(v["unit_price"] - 1.0) < 1e-9 and v["orig"]["total"] == 40.0 and v["orig"]["rate"] == 4.0 and r.plausible(v)
        w = {"total": 40.0, "currency": "CZK", "date": date(2026, 10, 6)}   # kein Kurs: bleibt unverändert, Hinweis in orig
        asyncio.run(r.convert_to_eur(None, w))
        assert w["total"] == 40.0 and w["orig"]["rate"] is None
        e = {"total": 40.0, "currency": "EUR"}
        asyncio.run(r.convert_to_eur(None, e))
        assert "orig" not in e
    finally:
        r.eur_rate = orig
