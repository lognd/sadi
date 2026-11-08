"""Tests for tools/check_typani_collisions.py (typani name-collision gate)."""

# frob:ticket 01M6W7R1T397W3C0JZV66MX8BW

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from typani import Err, Ok

_SCRIPT = Path(__file__).resolve().parents[2] / "tools" / "check_typani_collisions.py"
_spec = importlib.util.spec_from_file_location("check_typani_collisions", _SCRIPT)
assert _spec is not None and _spec.loader is not None
chk = importlib.util.module_from_spec(_spec)
sys.modules["check_typani_collisions"] = chk
_spec.loader.exec_module(chk)

REQUIRED = {"propagate", "catching", "Result", "Ok", "Err", "UnwrapError", "ErrorSet"}


def test_exports_cover_required_names() -> None:
    """The introspected typani exports include the names we must never shadow."""
    assert REQUIRED <= set(chk.typani_exports())


def test_sadi_uncertainty_has_no_collisions() -> None:
    """sadi.uncertainty.__all__ shares no name with typani."""
    assert chk.export_collisions() == Ok([])


def test_collision_is_detected(monkeypatch) -> None:
    """A re-exported typani name is reported."""
    import sadi.uncertainty as unc

    monkeypatch.setattr(unc, "__all__", [*unc.__all__, "propagate"])
    assert chk.export_collisions() == Ok(["propagate"])


def test_missing_module_is_err() -> None:
    """An unimportable module yields Err, not an exception."""
    assert isinstance(chk.export_collisions("sadi.no_such_module"), Err)


def test_no_alias_in_repo() -> None:
    """No python source aliases an import to a typani name."""
    assert chk.alias_collisions() == []


def test_alias_is_detected(tmp_path) -> None:
    """`import ... as propagate` is flagged; unrelated aliases are not."""
    (tmp_path / "bad.py").write_text("from sadi.uncertainty import uncertain as propagate\n")
    (tmp_path / "ok.py").write_text("import numpy as np\n")
    hits = chk.alias_collisions(tmp_path)
    assert len(hits) == 1 and "bad.py:1" in hits[0]


def test_typani_and_sadi_names_coexist() -> None:
    """typani.propagate and sadi.uncertainty.uncertain import side by side."""
    from typani import propagate

    from sadi.uncertainty import uncertain

    assert propagate is not uncertain
    assert callable(propagate) and callable(uncertain)


def test_main_exit_zero(capsys) -> None:
    """The CLI exits 0 and prints nothing on a clean tree."""
    assert chk.main() == 0
    assert capsys.readouterr().out == ""
