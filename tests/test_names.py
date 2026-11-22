"""Findet Namen, die in Funktionen benutzt, aber nirgends definiert sind (z. B. ein vergessenes ``msg``). python tests/test_names.py"""
import builtins
import importlib.util
import pathlib
import symtable

pkg = pathlib.Path(__file__).parent.parent / "custom_components" / "drive_energy_doc"
spec = importlib.util.spec_from_file_location("const", pkg / "const.py")
const = importlib.util.module_from_spec(spec)
spec.loader.exec_module(const)
star = set(dir(const))  # Namen aus „from .const import *“


def undefined(path):
    src = path.read_text(encoding="utf-8")
    top = symtable.symtable(src, path.name, "exec")
    defined = {s.get_name() for s in top.get_symbols() if s.is_assigned() or s.is_imported() or s.is_namespace()} | star | set(dir(builtins))
    bad = set()

    def walk(t):
        for s in t.get_symbols():
            if s.is_global() and s.is_referenced() and s.get_name() not in defined and not s.get_name().startswith("__"):
                bad.add((t.get_name(), s.get_name()))
        for c in t.get_children():
            walk(c)

    walk(top)
    return sorted(bad)


def test_no_undefined_names():
    problems = {p.name: undefined(p) for p in sorted(pkg.glob("*.py"))}
    problems = {k: v for k, v in problems.items() if v}
    assert not problems, problems


test_no_undefined_names()
print("ok test_no_undefined_names")
