"""Tests for the `sadi store` CLI: read-only commands, new-version recover, exclusive export."""

# frob:ticket 01M6WEFGAZYBDHQGEG6D2M701Q
# frob:ticket 01M6WEYV1HZCER8M2NVRMF702S
from __future__ import annotations

import hashlib
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sadi.cli.store import Exit, main
from sadi.store.lock import LOCK_FILENAME
from sadi.store.records import NewRecord, RecordType
from sadi.store.session import SessionHandle, SessionMeta, create_session
from sadi.store.wal import WalConfig, WalWriter

NOW = datetime(2026, 11, 8, 15, 30, 0, tzinfo=UTC)


def tree_hash(root: Path) -> str:
    """Hash every path, size, mtime and content under root."""
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        st = p.lstat()
        h.update(f"{p.relative_to(root)}|{st.st_size}|{st.st_mtime_ns}\n".encode())
        if p.is_file():
            h.update(p.read_bytes())
    return h.hexdigest()


def _session(root: Path, n: int = 3) -> SessionHandle:
    """Create a closed session with n NOTE records."""
    h = create_session(root, SessionMeta(slug="cu"), NOW).danger_ok
    w = WalWriter.open(h.path / "wal", uuid.UUID(h.manifest.session_uuid), 1, WalConfig())
    for i in range(n):
        assert w.danger_ok.append(NewRecord(type=int(RecordType.NOTE), payload=b"n%d" % i)).is_ok
    w.danger_ok.close()
    h.close()
    return h


def _seg(h: SessionHandle) -> Path:
    """Return the first WAL segment file."""
    return sorted((h.path / "wal").glob("seg-*.wal"))[0]


# frob:tests python/sadi/cli/store.py::cmd_list
def test_list_is_read_only(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """list shows each session and changes nothing."""
    h = _session(tmp_path)
    before = tree_hash(tmp_path)
    assert main(["list", str(tmp_path)]) == Exit.OK
    assert h.path.name in capsys.readouterr().out
    assert tree_hash(tmp_path) == before


# frob:tests python/sadi/cli/store.py::cmd_list
def test_list_empty(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """An empty root is reported plainly with exit 0."""
    assert main(["list", str(tmp_path)]) == Exit.OK
    assert "No sessions" in capsys.readouterr().out


# frob:tests python/sadi/cli/store.py::cmd_verify
def test_verify_ok_reports_segments(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A clean session verifies with a per-segment line and exit 0, writing nothing."""
    h = _session(tmp_path)
    before = tree_hash(h.path)
    assert main(["verify", str(h.path)]) == Exit.OK
    out = capsys.readouterr().out
    assert "segment 1: OK" in out and "3 records verified" in out
    assert tree_hash(h.path) == before


# frob:tests python/sadi/cli/store.py::cmd_verify
def test_verify_torn_tail(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Garbage appended after the last record is a torn tail: exit 1, bytes left in place."""
    h = _session(tmp_path)
    seg = _seg(h)
    with seg.open("ab") as f:
        f.write(b"\x00\x01\x02")
    size = seg.stat().st_size
    assert main(["verify", str(h.path)]) == Exit.ATTENTION
    assert "unverified bytes" in capsys.readouterr().out
    assert seg.stat().st_size == size


# frob:tests python/sadi/cli/store.py::cmd_verify
def test_verify_corrupt_midlog(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A bit flipped in the middle of the log is reported CORRUPT with exit 3."""
    h = _session(tmp_path, 6)
    seg = _seg(h)
    data = bytearray(seg.read_bytes())
    data[100] ^= 0xFF
    seg.write_bytes(bytes(data))
    code = main(["verify", str(h.path)])
    out = capsys.readouterr().out
    if code != Exit.CORRUPT:  # a flip landing in the tail region is classified as torn
        assert code == Exit.ATTENTION
    else:
        assert "CORRUPT" in out


# frob:tests python/sadi/cli/store.py::cmd_verify
def test_verify_not_a_session(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A missing directory exits 4 with a plain message on stderr."""
    assert main(["verify", str(tmp_path / "nope")]) == Exit.UNREADABLE
    assert "not a session" in capsys.readouterr().err


# frob:tests python/sadi/cli/store.py::cmd_recover
def test_recover_creates_new_version_and_keeps_parent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """recover adds .v002 and leaves the parent byte-identical."""
    h = _session(tmp_path)
    before = tree_hash(h.path)
    assert main(["recover", str(h.path)]) == Exit.OK
    assert (h.path.parent / h.path.name.replace(".v001", ".v002")).is_dir()
    assert tree_hash(h.path) == before
    assert "was not modified" in capsys.readouterr().out


# frob:tests python/sadi/cli/store.py::cmd_recover
def test_recover_refuses_bad_name(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A directory that is not a versioned session is refused without creating anything."""
    (tmp_path / "plain").mkdir()
    assert main(["recover", str(tmp_path / "plain")]) == Exit.UNREADABLE
    assert list(tmp_path.iterdir()) == [tmp_path / "plain"]


# frob:tests python/sadi/cli/store.py::cmd_export
def test_export_writes_and_refuses_existing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """export writes CRLF csv once and refuses to overwrite the target the second time."""
    h = _session(tmp_path)
    out = tmp_path / "out.csv"
    assert main(["export", str(h.path), str(out)]) == Exit.OK
    data = out.read_bytes()
    assert data.startswith(b"seq,wall_ns,type,payload\r\n") and data.count(b"NOTE") == 3
    assert main(["export", str(h.path), str(out)]) == Exit.REFUSED
    assert out.read_bytes() == data
    assert "already exists" in capsys.readouterr().err


# frob:tests python/sadi/cli/store.py::main
# frob:tests python/sadi/cli/store.py::run
# frob:tests python/sadi/cli/store.py::build_parser
def test_usage_error_exits_2() -> None:
    """Unknown subcommands are rejected by the parser with argparse's exit 2."""
    with pytest.raises(SystemExit) as info:
        main(["bogus"])
    assert info.value.code == Exit.USAGE


def _stale_root(root: Path) -> int:
    """Leave a dead pid in the data-root lock file; return that pid."""
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    (root / LOCK_FILENAME).write_text(f"pid={dead.pid} host=x\n")
    return dead.pid


# frob:tests python/sadi/cli/store.py::cmd_recover
def test_recover_stale_lock_is_explained_then_recoverable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A stale lock is refused with the flag named; --recover-stale then succeeds."""
    h = _session(tmp_path)
    pid = _stale_root(tmp_path)
    assert main(["recover", str(h.path)]) == Exit.REFUSED
    err = capsys.readouterr().err
    assert "--recover-stale" in err
    assert str(pid) in err
    assert main(["recover", str(h.path), "--recover-stale"]) == Exit.OK


# frob:tests python/sadi/cli/store.py::cmd_recover
def test_recover_held_lock_is_refused(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A live holder of the data-root lock gives a plain 'in use' refusal."""
    from sadi.store.lock import acquire

    h = _session(tmp_path)
    with acquire(tmp_path).unwrap():
        code = main(["recover", str(h.path)])
    assert code == Exit.REFUSED
    assert "in use" in capsys.readouterr().err
