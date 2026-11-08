"""Tests for versioned sessions: O_EXCL create, resume, lock, read-only open, crash safety."""

# frob:ticket 01M6W7R1VQHABR51SH64668M06
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sadi.store import failpoints, session
from sadi.store.lock import LOCK_FILENAME, LockHeld, LockStale
from sadi.store.manifest import Manifest, read_manifest, write_manifest
from sadi.store.records import NewRecord, RecordType
from sadi.store.session import (
    BadSessionName,
    Locked,
    ParentCorrupt,
    ParentIncomplete,
    RootLockFailed,
    SessionHandle,
    SessionIo,
    SessionMeta,
    TooManyVersions,
    create_session,
    open_readonly,
    probe_lock,
    read_lock_holder,
    resume_session,
)
from sadi.store.wal import WalConfig, WalWriter

NOW = datetime(2026, 11, 8, 15, 30, 0, tzinfo=UTC)
META = SessionMeta(slug="Copper Short!", lab_module="sadi.labs.lctt", specimen={"id": "cu1"})


@pytest.fixture(autouse=True)
def _reset() -> Iterator[None]:
    """Clear failpoints around each test."""
    failpoints.clear()
    yield
    failpoints.clear()


def tree_hash(root: Path) -> str:
    """Hash every path, size, mtime and content under root (proves byte-identical trees)."""
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        st = p.lstat()
        h.update(f"{p.relative_to(root)}|{st.st_size}|{st.st_mtime_ns}|{p.is_dir()}\n".encode())
        if p.is_file():
            h.update(p.read_bytes())
    return h.hexdigest()


def _new(tmp_path: Path) -> SessionHandle:
    """Create a session or fail the test."""
    r = create_session(tmp_path, META, NOW)
    assert r.is_ok, r
    return r.danger_ok


def _with_wal(h: SessionHandle, n: int = 3) -> None:
    """Write n durable records into the session WAL and close the writer."""
    w = WalWriter.open(h.path / "wal", uuid.UUID(h.manifest.session_uuid), 1, WalConfig())
    assert w.is_ok, w
    for i in range(n):
        assert w.danger_ok.append(
            NewRecord(type=int(RecordType.NOTE), payload=b"x" * 8 + bytes([i]))
        ).is_ok
    w.danger_ok.close()


# frob:tests python/sadi/store/session.py::create_session
def test_create_layout_lock_and_manifest(tmp_path: Path) -> None:
    """A new session has v001, subdirs, a lock line and a valid open manifest."""
    h = _new(tmp_path)
    assert h.path.name == "20261108T153000Z-copper-short.v001"
    for sub in ("wal", "snapshots", "exports"):
        assert (h.path / sub).is_dir()
    assert (h.path / "lock").read_text().startswith(f"pid={os.getpid()} ")
    m = read_manifest(h.path).danger_ok
    assert m is not None and m.state == "open" and m.version == 1 and m.parent is None
    assert m.specimen == {"id": "cu1"}
    assert h.close().is_ok


# frob:tests python/sadi/store/session.py::create_session
def test_collision_takes_next_version_and_never_touches_existing(tmp_path: Path) -> None:
    """A pre-existing v001 is left byte-identical; create takes v002 then v003."""
    first = _new(tmp_path)
    first.close()
    (first.path / "wal" / "sentinel").write_bytes(b"precious")
    before = tree_hash(first.path)
    second = _new(tmp_path)
    second.close()
    third = _new(tmp_path)
    assert second.path.name.endswith(".v002") and third.path.name.endswith(".v003")
    assert tree_hash(first.path) == before
    third.close()


# frob:tests python/sadi/store/session.py::create_session
def test_version_exhaustion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When every version is taken the result is TooManyVersions, nothing is reused."""
    monkeypatch.setattr(session, "MAX_VERSION", 2)
    _new(tmp_path).close()
    _new(tmp_path).close()
    r = create_session(tmp_path, META, NOW)
    assert r.is_err and isinstance(r.danger_err, TooManyVersions)


# frob:tests python/sadi/store/session.py::create_session
def test_mkdir_io_error_is_result(tmp_path: Path) -> None:
    """An injected mkdir failure returns Err(SessionIo) and creates nothing."""
    failpoints.configure({"session.mkdir.before": "error:28"})
    r = create_session(tmp_path, META, NOW)
    assert r.is_err and isinstance(r.danger_err, SessionIo)
    assert list((tmp_path / "sessions").iterdir()) == []


# frob:tests python/sadi/store/manifest.py::write_manifest
def test_manifest_replace_failure_keeps_old_manifest(tmp_path: Path) -> None:
    """A failure before the rename leaves the previous manifest intact."""
    h = _new(tmp_path)
    old = (h.path / "manifest.json").read_bytes()
    failpoints.configure({"session.manifest.before_replace": "error:5"})
    newer = h.manifest.model_copy(update={"state": "crashed"})
    assert write_manifest(h.path, newer).is_err
    assert (h.path / "manifest.json").read_bytes() == old
    h.close()


# frob:tests python/sadi/store/manifest.py::Manifest
def test_manifest_is_frozen(tmp_path: Path) -> None:
    """Manifest is immutable and round-trips through JSON."""
    h = _new(tmp_path)
    with pytest.raises(Exception, match="frozen"):
        h.manifest.__setattr__("state", "closed")
    assert Manifest.model_validate_json(h.manifest.model_dump_json()) == h.manifest
    h.close()


# frob:tests python/sadi/store/session.py::probe_lock
def test_live_lock_is_not_stolen_and_released_on_close(tmp_path: Path) -> None:
    """A held lock reports Locked with holder info; close frees it; the file is kept."""
    h = _new(tmp_path)
    r = probe_lock(h.path)
    assert r.is_err and isinstance(r.danger_err, Locked)
    assert r.danger_err.holder_alive is True
    assert f"pid={os.getpid()}" in r.danger_err.pid_hint
    h.close()
    assert probe_lock(h.path).is_ok
    assert (h.path / "lock").exists()


# frob:tests python/sadi/store/session.py::read_lock_holder
def test_stale_lock_file_is_free_and_judged_dead(tmp_path: Path) -> None:
    """A lock line from a dead or pid-reused process is stale: the OS lock is free."""
    d = tmp_path / "s.v001"
    d.mkdir()
    (d / "lock").write_text("pid=2147483646 start=1 host=h started=x\n")
    assert read_lock_holder(d)[1] is False
    assert probe_lock(d).is_ok
    (d / "lock").write_text(f"pid={os.getpid()} start=bogus host=h started=x\n")
    assert read_lock_holder(d) == (f"pid={os.getpid()} start=bogus host=h started=x", False)
    assert probe_lock(d).is_ok


# frob:tests python/sadi/store/session.py::resume_session
def test_resume_creates_new_version_with_parent_link(tmp_path: Path) -> None:
    """Resume of a closed session with a torn tail leaves the parent byte-identical."""
    h = _new(tmp_path)
    _with_wal(h)
    h.close()
    seg = next((h.path / "wal").glob("seg-*.wal"))
    with seg.open("ab") as f:
        f.write(b"\x00torn-tail-garbage")
    before = tree_hash(h.path)
    r = resume_session(h.path)
    assert r.is_ok, r
    child = r.danger_ok
    assert child.path.name.endswith(".v002") and child.path != h.path
    assert child.manifest.parent == h.path.name
    assert child.manifest.parent_last_seq is not None and child.manifest.parent_last_seq >= 3
    assert tree_hash(h.path) == before
    child.close()


# frob:tests python/sadi/store/session.py::resume_session
def test_resume_refuses_locked_incomplete_corrupt_and_bad_name(tmp_path: Path) -> None:
    """Resume refuses a live-locked, WAL-less, corrupt or oddly named parent."""
    h = _new(tmp_path)
    locked = resume_session(h.path)
    assert locked.is_err and isinstance(locked.danger_err, RootLockFailed)
    _with_wal(h, 5)
    h.close()
    seg = next((h.path / "wal").glob("seg-*.wal"))
    raw = bytearray(seg.read_bytes())
    raw[100] ^= 0xFF  # corrupt an early frame with valid frames after it
    seg.write_bytes(bytes(raw))
    before = tree_hash(h.path)
    bad = resume_session(h.path)
    assert bad.is_err and isinstance(bad.danger_err, ParentCorrupt)
    assert tree_hash(h.path) == before
    assert len(list(h.path.parent.iterdir())) == 1
    inc = tmp_path / "sessions" / "x.v001"
    inc.mkdir()
    assert isinstance(resume_session(inc).danger_err, ParentIncomplete)
    odd = tmp_path / "odd"
    odd.mkdir()
    assert isinstance(resume_session(odd).danger_err, BadSessionName)


# frob:tests python/sadi/store/session.py::open_readonly
def test_open_readonly_is_byte_identical(tmp_path: Path) -> None:
    """Read-only open and drop never mutates: closed, locked, torn, no-manifest, bad-manifest."""
    closed = _new(tmp_path)
    _with_wal(closed)
    closed.close()
    seg = next((closed.path / "wal").glob("seg-*.wal"))
    with seg.open("ab") as f:
        f.write(b"\x01tail")
    nomf = _new(tmp_path)
    nomf.close()
    (nomf.path / "manifest.json").unlink()
    badmf = _new(tmp_path)
    badmf.close()
    (badmf.path / "manifest.json").write_text("{not json")
    live = create_session(tmp_path, SessionMeta(slug="live"), NOW).danger_ok
    root = tmp_path / "sessions"
    before = tree_hash(root)
    for d in sorted(root.iterdir()):
        r = open_readonly(d)
        assert r.is_ok, r
    assert tree_hash(root) == before
    assert open_readonly(nomf.path).danger_ok.manifest_stale
    assert open_readonly(badmf.path).danger_ok.manifest_error is not None
    assert open_readonly(live.path).danger_ok.holder_alive is True
    assert tree_hash(root) == before
    live.close()


_CRASH = """
import sys
from datetime import datetime, UTC
from pathlib import Path
from sadi.store.session import create_session, SessionMeta
create_session(Path(sys.argv[1]), SessionMeta(), datetime(2026, 1, 1, tzinfo=UTC))
"""


# frob:tests python/sadi/store/session.py::create_session
@pytest.mark.parametrize(
    "spec",
    [
        "session.mkdir.before=kill",
        "session.lock.after=kill",
        "session.manifest.write=kill",
        "session.manifest.before_replace=kill",
        "durable.rename=nth:2:kill",
    ],
)
def test_crash_during_create_never_reuses_directory(tmp_path: Path, spec: str) -> None:
    """Killing create anywhere leaves at most an incomplete dir; retry takes a new version."""
    env = {**os.environ, "SADI_FAILPOINTS": spec}
    p = subprocess.run([sys.executable, "-c", _CRASH, str(tmp_path)], env=env, check=False)
    assert p.returncode == 137
    sessions = tmp_path / "sessions"
    survivors = {d.name: tree_hash(d) for d in sessions.iterdir()}
    when = datetime(2026, 1, 1, tzinfo=UTC)
    refused = create_session(tmp_path, SessionMeta(), when)
    if (tmp_path / LOCK_FILENAME).read_text():  # killed after the data-root lock was taken
        assert refused.is_err and isinstance(refused.danger_err, RootLockFailed)
        assert isinstance(refused.danger_err.error, LockStale)
    r = create_session(tmp_path, SessionMeta(), when, recover_stale=True)
    assert r.is_ok, r
    assert r.danger_ok.path.name not in survivors
    for name, digest in survivors.items():
        assert tree_hash(sessions / name) == digest
        assert open_readonly(sessions / name).is_ok
    r.danger_ok.close()


# frob:tests python/sadi/store/session.py::SessionHandle.close
def test_close_writes_closed_manifest_and_is_idempotent(tmp_path: Path) -> None:
    """Close atomically records state=closed, releases the lock and may be repeated."""
    h = _new(tmp_path)
    assert h.close().is_ok
    assert h.close().is_ok
    m = read_manifest(h.path).danger_ok
    assert m is not None and m.state == "closed" and m.closed is not None


# frob:tests python/sadi/store/session.py::create_session
def test_second_open_of_same_root_is_lock_held(tmp_path: Path) -> None:
    """A second create or resume on a locked root is Err(LockHeld) with the holder pid."""
    h = _new(tmp_path)
    again = create_session(tmp_path, META, NOW)
    assert again.is_err and isinstance(again.danger_err, RootLockFailed)
    err = again.danger_err.error
    assert isinstance(err, LockHeld) and err.pid == os.getpid()
    resumed = resume_session(h.path)
    assert resumed.is_err and isinstance(resumed.danger_err, RootLockFailed)
    assert isinstance(resumed.danger_err.error, LockHeld)
    assert [d.name for d in (tmp_path / "sessions").iterdir()] == [h.path.name]
    h.close()


# frob:tests python/sadi/store/session.py::SessionHandle.close
def test_close_releases_data_root_lock(tmp_path: Path) -> None:
    """After close the root can be opened again and the lock file is marked clean."""
    h = _new(tmp_path)
    assert (tmp_path / LOCK_FILENAME).read_text().startswith("pid=")
    h.close()
    assert (tmp_path / LOCK_FILENAME).read_text() == ""
    nxt = create_session(tmp_path, META, NOW)
    assert nxt.is_ok, nxt
    resumed_blocked = resume_session(h.path)
    assert resumed_blocked.is_err
    nxt.danger_ok.close()
    res = resume_session(h.path)
    assert res.is_err and not isinstance(res.danger_err, RootLockFailed)  # no WAL: ParentIncomplete
    assert (tmp_path / LOCK_FILENAME).read_text() == ""


# frob:tests python/sadi/store/session.py::create_session
def test_stale_data_root_lock_is_reported_not_taken(tmp_path: Path) -> None:
    """A dead holder's lock gives Err(LockStale) untouched; recover_stale is explicit."""
    lock = tmp_path / LOCK_FILENAME
    lock.write_text("pid=999999 host=x\n")
    r = create_session(tmp_path, META, NOW)
    assert r.is_err and isinstance(r.danger_err, RootLockFailed)
    assert isinstance(r.danger_err.error, LockStale) and r.danger_err.error.pid == 999999
    assert lock.read_text() == "pid=999999 host=x\n"
    assert not (tmp_path / "sessions").exists() or not list((tmp_path / "sessions").iterdir())
    ok = create_session(tmp_path, META, NOW, recover_stale=True)
    assert ok.is_ok, ok
    ok.danger_ok.close()
