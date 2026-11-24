"""Kennzeichen-SVG: python tests/test_plate.py"""
import importlib.util, pathlib, sys, xml.dom.minidom

spec = importlib.util.spec_from_file_location("plate", pathlib.Path(__file__).parent.parent / "custom_components" / "drive_energy_doc" / "plate.py")
m = importlib.util.module_from_spec(spec); sys.modules["plate"] = m; spec.loader.exec_module(m)


def test_valid_xml_for_all_countries():
    for cc, ex in m.EXAMPLES.items():
        xml.dom.minidom.parseString(m.svg("X", cc, ex))


def test_yellow_and_strip():
    assert "#f7c600" in m.svg("NL", "NL", "AB-123-C") and "#f7c600" in m.svg("UK", "GB", "AB12 CDE")
    assert "#f7c600" not in m.svg("D", "DE", "B-AB 1234")
    assert "#003399" in m.svg("D", "DE", "B-AB 1234") and "#003399" not in m.svg("CH", "CH", "ZH 123456")


def test_text_is_sanitized():
    out = m.svg("D", "DE", "<script>alert(1)</script>")
    assert "<script" not in out and "(" not in out and ")" not in out
    xml.dom.minidom.parseString(out)


def test_europe_ring_only_for_eu():
    for cc in ("DE", "NL", "FR", "AT", "PL"):
        assert m.svg("X", cc, "AB 12").count("<polygon") == 12, cc          # zwölf Sterne
    for cc in ("CH", "NO", "GB", "US", "UA", "RS"):
        assert "<polygon" not in m.svg("X", cc, "AB 12"), cc
    assert set(m.EU) <= set(m.EXAMPLES)


def test_empty_text_uses_example():
    out = m.svg("D", "DE", "")   # Deutschland: Ortskennung und Rest sind durch die Plaketten getrennt
    assert ">B</text>" in out and ">AB 1234</text>" in out
    assert "AB 12 345" not in m.svg("DK", "DK", "") and "AF 54554" in m.svg("DK", "DK", "")


def test_country_formats():
    assert m.format_text("CH", "SG197052") == "SG·197 052" and m.format_text("CH", "ZH 123456") == "ZH·123 456" and m.format_text("CH", "VD 1234") == "VD·1 234"
    assert m.format_text("GB", "AB12EHJ") == "AB12 EHJ" and m.format_text("BE", "1ABC003") == "1-ABC-003" and m.format_text("FR", "AB123CD") == "AB-123-CD"
    assert "&#183;" in m.svg("CH", "CH", "SG197052") and "#b01c2e" in m.svg("B", "BE", "1ABC003") and "#c8102e" in m.svg("DK", "DK", "AF 54554")
    assert m.format_text("SE", "ABC123") == "ABC 123" and m.format_text("NO", "AB12345") == "AB 12345" and m.format_text("SK", "BA123AB") == "BA-123AB"
    assert m.format_text("HR", "ZG1234AB") == "ZG 1234-AB" and m.format_text("RU", "A123BC77") == "A123BC 77" and m.format_text("PT", "12AB34") == "12-AB-34"
    assert "#da291c" in m.svg("CH", "CH", "SG197052") and "#012169" in m.svg("GB", "GB", "AB12EHJ")


for n, fn in list(globals().items()):
    if n.startswith("test_"):
        fn(); print("ok", n)
