"""Startup spill recovery: the lifespan imports spills once the data-root lock is held."""

# frob:ticket 01M6WP4WV9B3SCJ0GY2M32XWZV
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from sadi.server.app import AppSettings, create_app
from sadi.store.records import RecordType, encode_frame
from sadi.store.wal import encode_segment_header


def _spill(path: Path, n: int = 3, garbage: bool = False) -> bytes:
    """Write a spill file (or a headerless garbage file) and return its bytes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if garbage:
        data = b"not a wal segment" * 8
    else:
        data = encode_segment_header(1, 1, uuid.uuid4())
        for i in range(n):
            data += encode_frame(int(RecordType.NOTE), 1 + i, 1000 + i, 0, bytes([i]) * 20)
    path.write_bytes(data)
    return data


def _versions(root: Path) -> list[Path]:
    """Return session version dirs created under the data root (excluding spill/)."""
    if not root.is_dir():
        return []
    return [p for p in root.iterdir() if p.is_dir() and p.name != "spill"]


# frob:tests python/sadi/server/app.py::_lifespan
def test_spill_at_startup_imported_as_new_version(tmp_path: Path) -> None:
    """A spill in the data root becomes a new session version and the file is kept."""
    root = tmp_path / "root"
    data = _spill(root / "spill" / "s.wal")
    app = create_app(AppSettings(data_root=root))
    with TestClient(app):
        assert app.state.spill_failures == 0
    assert len(_versions(root)) == 1
    assert (root / "spill" / "s.wal").read_bytes() == data


# frob:tests python/sadi/server/app.py::_import_spills
def test_failed_spill_import_leaves_file_intact(tmp_path: Path) -> None:
    """A corrupt spill is reported as a failure, startup proceeds, the file is untouched."""
    root = tmp_path / "root"
    data = _spill(root / "spill" / "bad.wal", garbage=True)
    app = create_app(AppSettings(data_root=root))
    with TestClient(app):
        assert app.state.spill_failures == 1
    assert (root / "spill" / "bad.wal").read_bytes() == data
    assert _versions(root) == []


# frob:tests python/sadi/server/app.py::_import_spills
def test_no_spill_is_noop(tmp_path: Path) -> None:
    """With no spill files nothing is created and there are no failures."""
    root = tmp_path / "root"
    app = create_app(AppSettings(data_root=root))
    with TestClient(app):
        assert app.state.spill_failures == 0
    assert _versions(root) == []
