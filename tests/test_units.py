import importlib, pathlib, sys, types
pkg_dir = pathlib.Path(__file__).parent.parent / "custom_components" / "drive_energy_doc"
if "drive_energy_doc" not in sys.modules:
    pkg = types.ModuleType("drive_energy_doc"); pkg.__path__ = [str(pkg_dir)]; sys.modules["drive_energy_doc"] = pkg   # Paket ohne Home Assistant laden
u = importlib.import_module("drive_energy_doc.units")


def _hass(length, country=""):
    class H:
        class config:
            pass
    H.config.units = types.SimpleNamespace(length_unit=length)
    H.config.country = country
    return H


def test_system():
    assert u.system(_hass("km", "DE"))["sys"] == "metric"
    us = u.system(_hass("mi", "US"))
    assert us["dist"] == "mi" and us["vol"] == "gal" and us["cons"] == "mpg"
    gb = u.system(_hass("mi", "GB"))
    assert gb["dist"] == "mi" and gb["vol"] == "l" and gb["mpg_l"] == u.L_PER_GAL_UK   # GB: Meilen, Liter an der Säule, mpg mit britischer Gallone
    assert u.system(None)["sys"] == "metric"


def test_conversions():
    us = u.system(_hass("mi", "US"))
    assert abs(u.to_km(100, "mi") - 160.9344) < 1e-9 and u.to_km(100, "km") == 100
    assert abs(u.to_l(10, "gal", us) - 37.85411784) < 1e-9
    assert abs(u.price_to_per_l(3.785411784, "gal", us) - 1.0) < 1e-9
    assert abs(u.dist(us, 160.9344) - 100) < 1e-9 and abs(u.vol(us, 3.785411784) - 1) < 1e-9
    # 7,84 l/100 km = 30 mpg (US); 6 l/100 km = 47,1 mpg (GB)
    assert abs(u.cons(us, 7.8404, False) - 30.0) < 0.01
    assert abs(u.cons(u.system(_hass("mi", "GB")), 6.0, False) - 47.08) < 0.02
    assert abs(u.cons(us, 20.0, True) - 32.18688) < 1e-6   # kWh/100 km -> kWh/100 mi
    assert u.cons_unit(us, False) == "mpg" and u.cons_unit(us, True) == "kWh/100 mi" and u.cons_unit(u.system(None), False) == "l/100 km"
    m = u.system(None)
    assert u.dist(m, 100) == 100 and u.vol(m, 40) == 40 and u.cons(m, 6.5, False) == 6.5
