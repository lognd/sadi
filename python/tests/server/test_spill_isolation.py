"""Server tests never scan the real user data dir or OS temp dir at startup."""

# frob:ticket 01M6WPBZK1AYHDYR3RSR656D8Z
# frob:ticket 01M6WQ6E3HVJC599WZJVBT39Q9
from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sadi.server.app import AppSettings, create_app
from sadi.store.records import RecordType, encode_frame
from sadi.store.spill import MARKER_SUFFIX, SPILL_DIRNAME, discover_spills, user_data_dir
from sadi.store.wal import encode_segment_header


def _plant_spill(spill_dir: Path) -> Path:
    """Write a valid emergency spill into `spill_dir` and return its path."""
    spill_dir.mkdir(parents=True)
    data = encode_segment_header(1, 1, uuid.uuid4()) + encode_frame(
        int(RecordType.NOTE), 1, 1000, 0, b"x" * 20
    )
    path = spill_dir / "s.wal"
    path.write_bytes(data)
    os.utime(path, (1_000_000_000, 1_000_000_000))
    return path


def _imported(spill: Path) -> bool:
    """Return True when the app wrote an import marker beside `spill`."""
    return spill.with_name(spill.name + MARKER_SUFFIX).exists()


def _start(root: Path) -> None:
    """Start and stop the app once against `root`, requiring no spill failures."""
    app = create_app(AppSettings(data_root=root))
    with TestClient(app):
        assert app.state.spill_failures == 0


# frob:tests python/sadi/server/app.py::_lifespan
def test_startup_ignores_spill_in_real_dir_standin(
    tmp_path: Path, isolated_spill_dirs: tuple[Path, Path]
) -> None:
    """A spill in the real user dir stand-in is neither imported, modified nor deleted."""
    user_dir, _temp = isolated_spill_dirs
    assert user_data_dir() == user_dir
    # Stand-in for the real XDG dir: the spill dir the scanner WOULD read un-isolated.
    real = tmp_path / "real-home" / "xdg" / "sadi" / SPILL_DIRNAME
    planted = _plant_spill(real)
    before = (planted.read_bytes(), planted.stat().st_mtime_ns)
    root = tmp_path / "root"
    _start(root)
    assert planted.exists()
    assert (planted.read_bytes(), planted.stat().st_mtime_ns) == before
    assert not _imported(planted)
    assert sorted(p.name for p in real.iterdir()) == ["s.wal"]
    assert discover_spills(root) == []
    assert [p for p in root.iterdir() if p.is_dir() and p.name != "spill"] == []


# frob:tests python/sadi/server/app.py::_lifespan
def test_control_spill_in_scanned_data_root_is_imported(
    tmp_path: Path, isolated_spill_dirs: tuple[Path, Path]
) -> None:
    """Negative control: the same spill in the app's own data root IS imported."""
    root = tmp_path / "root"
    planted = _plant_spill(root / SPILL_DIRNAME)
    _start(root)
    assert _imported(planted)
    assert [p for p in root.iterdir() if p.is_dir() and p.name != "spill"] != []


# frob:tests python/sadi/server/app.py::_lifespan
def test_control_standin_spill_is_imported_without_isolation(
    tmp_path: Path, isolated_spill_dirs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Negative control: pointing XDG/HOME at the stand-in makes the app import its spill."""
    xdg = tmp_path / "real-home" / "xdg"
    planted = _plant_spill(xdg / "sadi" / SPILL_DIRNAME)
    monkeypatch.setenv("HOME", str(tmp_path / "real-home"))
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg))
    monkeypatch.setenv("LOCALAPPDATA", str(xdg))
    assert planted in discover_spills(tmp_path / "root")
    _start(tmp_path / "root")
    assert _imported(planted)
