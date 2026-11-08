"""Tests for the persisted plugin enable/disable state."""

# frob:ticket 01M6WFZF75SH31V398E8P7WC5Y
from __future__ import annotations

import os
from pathlib import Path

from sadi.plugins import state
from sadi.plugins.state import PluginStateError, load_disabled, set_enabled, state_path


# frob:tests python/sadi/plugins/state.py::load_disabled
# frob:tests python/sadi/plugins/state.py::state_path
def test_missing_file_means_nothing_disabled(tmp_path: Path) -> None:
    """No file yields an empty set."""
    assert load_disabled(tmp_path).danger_ok == frozenset()


# frob:tests python/sadi/plugins/state.py::set_enabled
def test_disable_enable_roundtrip(tmp_path: Path) -> None:
    """Disable persists, enable removes, and no temp files linger."""
    assert set_enabled(tmp_path / "cfg", "a", False).danger_ok == {"a"}
    assert load_disabled(tmp_path / "cfg").danger_ok == {"a"}
    assert set_enabled(tmp_path / "cfg", "a", True).danger_ok == frozenset()
    assert [p.name for p in (tmp_path / "cfg").iterdir()] == ["plugins.json"]


# frob:tests python/sadi/plugins/state.py::set_enabled
def test_corrupt_file_is_kept_aside_not_overwritten(tmp_path: Path) -> None:
    """A damaged file survives byte-for-byte under a .corrupt name and the error names it."""
    state_path(tmp_path).write_text("{not json", encoding="utf-8")
    res = set_enabled(tmp_path, "a", False)
    assert res.is_err and res.danger_err is PluginStateError.Corrupt
    asides = list(tmp_path.glob("plugins.json.corrupt-*"))
    assert len(asides) == 1 and asides[0].read_text() == "{not json"
    assert str(asides[0]) in "; ".join(res.notes)
    assert not state_path(tmp_path).exists()
    assert set_enabled(tmp_path, "a", False).is_ok


# frob:tests python/sadi/plugins/state.py::load_disabled
def test_load_corrupt_does_not_touch_file(tmp_path: Path) -> None:
    """Reading a damaged file reports Corrupt and leaves it in place."""
    state_path(tmp_path).write_text('{"disabled": 3}', encoding="utf-8")
    assert load_disabled(tmp_path).danger_err is PluginStateError.Corrupt
    assert state_path(tmp_path).read_text() == '{"disabled": 3}'


# frob:tests python/sadi/plugins/state.py::set_enabled
def test_failed_write_keeps_old_state(tmp_path: Path, monkeypatch) -> None:
    """If the rename fails the previous file is intact and no temp file remains."""
    assert set_enabled(tmp_path, "a", False).is_ok

    def boom(*_a: object, **_k: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(state.os, "replace", boom)
    res = set_enabled(tmp_path, "b", False)
    assert res.danger_err is PluginStateError.WriteFailed
    monkeypatch.undo()
    assert load_disabled(tmp_path).danger_ok == {"a"}
    assert [p.name for p in tmp_path.iterdir()] == ["plugins.json"]
    _ = os
