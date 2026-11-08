"""Held-root session wrappers: create and resume while the caller already owns the root lock."""

# frob:ticket 01M6W7R3XY1B0BF689RX3H80G2

from __future__ import annotations

import uuid
from pathlib import Path

from sadi.store.lock import acquire
from sadi.store.session import (
    SessionMeta,
    create_session_in_held_root,
    resume_session_in_held_root,
)
from sadi.store.writer_thread import WriterHandle


# frob:tests python/sadi/store/session.py::create_session_in_held_root
# frob:tests python/sadi/store/session.py::resume_session_in_held_root
def test_create_and_resume_under_held_lock(tmp_path: Path) -> None:
    """With the root flock held by the caller, create then resume yields a child version."""
    lock = acquire(tmp_path, recover_stale=False).danger_ok
    try:
        made = create_session_in_held_root(tmp_path, SessionMeta(slug="s", lab_module="lctt"))
        assert made.is_ok, made
        h = made.danger_ok
        parent = h.path
        w = WriterHandle.open(parent / "wal", uuid.UUID(h.manifest.session_uuid), first_seq=1)
        assert w.danger_ok.close().is_ok
        assert h.close().is_ok
        child = resume_session_in_held_root(parent)
        assert child.is_ok, child
        assert child.danger_ok.manifest.parent == parent.name
        assert child.danger_ok.close().is_ok
        assert resume_session_in_held_root(tmp_path / "nope").is_err
    finally:
        lock.release()
