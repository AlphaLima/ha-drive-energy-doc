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
    assert "B-AB 1234" in m.svg("D", "DE", "")


for n, fn in list(globals().items()):
    if n.startswith("test_"):
        fn(); print("ok", n)
