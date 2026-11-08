"""Real-store tests of the read-only SESS/WAL survey using tmp_path sessions."""

# frob:ticket 01M6WJHRTR9DZMZGR04GT1SN0C
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from sadi.doctor.sessions import survey_sessions
from sadi.store.records import NewRecord, RecordType
from sadi.store.session import SessionHandle, SessionMeta, create_session
from sadi.store.wal import WalConfig, WalWriter

NOW = datetime(2026, 11, 8, 15, 30, 0, tzinfo=UTC)


def _make(root: Path, records: int = 3) -> SessionHandle:
    """Create a session under root with a few NOTE records, left open (unclosed)."""
    h = create_session(root, SessionMeta(slug="demo"), NOW).unwrap()
    w = WalWriter.open(h.path / "wal", uuid.UUID(h.manifest.session_uuid), 1, WalConfig()).unwrap()
    for i in range(records):
        w.append(NewRecord(type=int(RecordType.NOTE), payload=f"n{i}".encode())).unwrap()
    w.close()
    return h


def _seg(h: SessionHandle) -> Path:
    return h.path / "wal" / "seg-000001.wal"


def _snapshot(path: Path) -> dict[str, bytes]:
    return {str(p): p.read_bytes() for p in sorted(path.rglob("*")) if p.is_file()}


# frob:tests python/sadi/doctor/sessions.py::survey_sessions
def test_healthy_session_is_clean(tmp_path: Path) -> None:
    """A closed, intact session yields ok facts."""
    h = _make(tmp_path)
    h.close()
    (s,) = survey_sessions(str(tmp_path))
    assert (s.name_ok, s.wal, s.manifest) == (True, "ok", "ok")
    assert s.tail_bytes == 0 and s.last_seq == 3 and s.state == "closed"


# frob:tests python/sadi/doctor/sessions.py::survey_sessions
def test_torn_tail_is_reported_and_untouched(tmp_path: Path) -> None:
    """Trailing garbage reports torn-tail and no byte on disk changes."""
    h = _make(tmp_path)
    h.close()
    with _seg(h).open("ab") as f:
        f.write(b"\x01\x02\x03\x04\x05")
    before = _snapshot(h.path)
    (s,) = survey_sessions(str(tmp_path))
    assert s.wal == "torn-tail" and s.tail_bytes > 0
    assert _snapshot(h.path) == before


# frob:tests python/sadi/doctor/sessions.py::survey_sessions
def test_corrupt_segment_is_reported(tmp_path: Path) -> None:
    """A flipped byte inside a record is reported as non-ok, never repaired."""
    h = _make(tmp_path, records=6)
    h.close()
    data = bytearray(_seg(h).read_bytes())
    data[64 + 20] ^= 0xFF
    _seg(h).write_bytes(bytes(data))
    before = _snapshot(h.path)
    (s,) = survey_sessions(str(tmp_path))
    assert s.wal in ("corrupt", "torn-tail", "seal-mismatch", "seq-gap")
    assert s.wal != "ok"
    assert _snapshot(h.path) == before


# frob:tests python/sadi/doctor/sessions.py::survey_sessions
def test_stale_lock_is_reported(tmp_path: Path) -> None:
    """An unclosed session whose lock names a dead pid shows a dead holder."""
    h = _make(tmp_path)
    lock = h.path / "lock"
    lock.write_text("pid=999999 start=0 host=x\n")
    (s,) = survey_sessions(str(tmp_path))
    assert s.lock_holder
    assert s.holder_alive is not True


# frob:tests python/sadi/doctor/sessions.py::survey_sessions
def test_missing_manifest_is_stale(tmp_path: Path) -> None:
    """Deleting the derived manifest (as a crash might) is reported, not recreated."""
    h = _make(tmp_path)
    h.close()
    (h.path / "manifest.json").unlink()
    (s,) = survey_sessions(str(tmp_path))
    assert s.manifest == "missing" and s.manifest_stale
    assert not (h.path / "manifest.json").exists()


# frob:tests python/sadi/doctor/sessions.py::survey_sessions
def test_foreign_dir_and_no_root(tmp_path: Path) -> None:
    """Foreign folders are flagged; a missing sessions dir gives an empty survey."""
    assert survey_sessions(str(tmp_path)) == []
    (tmp_path / "sessions" / "notes").mkdir(parents=True)
    (s,) = survey_sessions(str(tmp_path))
    assert not s.name_ok and s.incomplete


# frob:tests python/sadi/doctor/checks/sess.py::survey
# frob:tests python/sadi/doctor/checks/sess.py::hits
# frob:tests python/sadi/doctor/checks/sess.py::listing
# frob:tests python/sadi/doctor/checks/sess.py::first_path
# frob:tests python/sadi/doctor/sessions.py::SessionFacts.incomplete
def test_check_helpers() -> None:
    """The shared check helpers select, list and locate sessions without side effects."""
    from doctor_fakes import FakeProbes

    from sadi.doctor.checks.sess import first_path, hits, listing, survey
    from sadi.doctor.registry import Ctx, ok
    from sadi.doctor.schema import Os, RunOptions
    from sadi.doctor.sessions import SessionFacts

    rows = [
        SessionFacts(name="a", path="/p/a", name_ok=True),
        SessionFacts(name="b", path="/p/b", name_ok=False),
    ]
    p = FakeProbes()
    p.sessions = rows
    ctx = Ctx(os=Os.LINUX, probes=p, options=RunOptions(data_root="/r"), data_root="/r")
    assert survey(ctx) == rows
    assert hits(rows, lambda s: s.name_ok) == rows[:1]
    assert rows[0].incomplete
    assert listing(Os.WINDOWS, "C:/x").startswith("Get-ChildItem")
    assert listing(Os.LINUX, "/x") == "ls -la '/x'"
    assert first_path(ok("x", paths=["/p/a"]), ctx) == "/p/a"
    assert first_path(ok("x"), ctx) == "/r/sessions"
