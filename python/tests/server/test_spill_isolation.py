"""Server tests never scan the real user data dir or OS temp dir at startup."""

# frob:ticket 01M6WPBZK1AYHDYR3RSR656D8Z
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from sadi.server.app import AppSettings, create_app
from sadi.store.records import RecordType, encode_frame
from sadi.store.spill import discover_spills, user_data_dir
from sadi.store.wal import encode_segment_header


# frob:tests python/sadi/server/app.py::_lifespan
def test_startup_ignores_spill_in_real_dir_standin(
    tmp_path: Path, isolated_spill_dirs: tuple[Path, Path]
) -> None:
    """A spill planted in the (redirected) real user dir is not seen once isolated elsewhere."""
    user_dir, _temp = isolated_spill_dirs
    assert user_data_dir() == user_dir
    # Plant in a stand-in for the real dir (NOT the redirected one).
    real = tmp_path / "real-user" / "sadi" / "spill"
    real.mkdir(parents=True)
    data = encode_segment_header(1, 1, uuid.uuid4()) + encode_frame(
        int(RecordType.NOTE), 1, 1000, 0, b"x" * 20
    )
    (real / "s.wal").write_bytes(data)
    root = tmp_path / "root"
    app = create_app(AppSettings(data_root=root))
    with TestClient(app):
        assert app.state.spill_failures == 0
    assert discover_spills(root) == []
    assert [p for p in root.iterdir() if p.is_dir() and p.name != "spill"] == []
