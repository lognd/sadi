"""The sadi-py conftest skips collection only when the extension is truly absent."""

# frob:ticket 01M6Z3V40NSSQZY6D4BVFV301C
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

_CONFTEST = Path(__file__).resolve().parents[3] / "crates" / "sadi-py" / "conftest.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("sadi_py_conftest", _CONFTEST)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# frob:tests crates/sadi-py/conftest.py::extension_missing
def test_missing_extension_reports_true(monkeypatch: pytest.MonkeyPatch) -> None:
    """A ModuleNotFoundError for sadi_py means skip."""
    mod = _load()
    monkeypatch.setitem(sys.modules, "sadi_py", None)  # forces ModuleNotFoundError name=sadi_py
    assert mod.extension_missing() is True


# frob:tests crates/sadi-py/conftest.py::extension_missing
def test_other_import_error_still_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """A different missing module inside a built extension must propagate, not skip."""
    mod = _load()

    def boom(name: str) -> None:
        raise ModuleNotFoundError("no dep", name="some_other_dep")

    monkeypatch.setattr(mod.importlib, "import_module", boom)
    with pytest.raises(ModuleNotFoundError):
        mod.extension_missing()


# frob:tests crates/sadi-py/conftest.py::pytest_ignore_collect
def test_ignore_collect_only_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test files are ignored when absent and collected when present."""
    mod = _load()
    f = Path("x/test_a.py")
    monkeypatch.setattr(mod, "extension_missing", lambda: True)
    assert mod.pytest_ignore_collect(f, None) is True
    monkeypatch.setattr(mod, "extension_missing", lambda: False)
    assert mod.pytest_ignore_collect(f, None) is None
