"""Tests for the data-root lock: exclusion across processes, stale reporting, release."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from typani import Err, Ok

from sadi.store.lock import (
    LOCK_FILENAME,
    LockHeld,
    LockStale,
    acquire,
    pid_alive,
    read_holder_pid,
)

_HOLDER = (
    "import sys,time\nfrom pathlib import Path\nfrom sadi.store.lock import acquire\n"
    "r=acquire(Path(sys.argv[1]))\nlk=r.unwrap()\nprint('READY',flush=True)\n"
    "sys.stdin.readline()\nlk.release()\n"
)


# frob:tests python/sadi/store/lock.py::DataRootLock.__init__
# frob:tests python/sadi/store/lock.py::acquire
# frob:tests python/sadi/store/lock.py::DataRootLock.held
# frob:tests python/sadi/store/lock.py::DataRootLock.release
# frob:tests python/sadi/store/lock.py::DataRootLock.__enter__
# frob:tests python/sadi/store/lock.py::DataRootLock.__exit__
def test_acquire_and_release(tmp_path: Path) -> None:
    """Acquire succeeds, release marks the file clean and allows reacquire."""
    match acquire(tmp_path):
        case Ok(lock):
            assert lock.held
            lock.release()
            lock.release()
            assert not lock.held
        case Err(e):
            raise AssertionError(e)
    assert (tmp_path / LOCK_FILENAME).read_text() == ""
    with acquire(tmp_path).unwrap():
        pass


# frob:tests python/sadi/store/lock.py::acquire
def test_second_process_gets_lockheld_with_pid(tmp_path: Path) -> None:
    """A second process sees LockHeld naming the holder pid; lock file is left intact."""
    proc = subprocess.Popen(
        [sys.executable, "-c", _HOLDER, str(tmp_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert proc.stdout is not None
        lines = iter(proc.stdout.readline, "")
        assert any(ln.strip() == "READY" for ln in lines)
        match acquire(tmp_path):
            case Err(LockHeld() as e):
                assert e.pid == proc.pid
            case other:
                raise AssertionError(other)
    finally:
        assert proc.stdin is not None
        proc.stdin.close()
        proc.wait(timeout=10)
    with acquire(tmp_path).unwrap():
        pass


# frob:tests python/sadi/store/lock.py::acquire
def test_stale_lock_reported_and_only_recovered_explicitly(tmp_path: Path) -> None:
    """A dead pid in a free lock file is reported as LockStale, never silently broken."""
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    (tmp_path / LOCK_FILENAME).write_text(f"pid={dead.pid} host=x\n")
    match acquire(tmp_path):
        case Err(LockStale() as e):
            assert e.pid == dead.pid
        case other:
            raise AssertionError(other)
    assert str(dead.pid) in (tmp_path / LOCK_FILENAME).read_text()
    with acquire(tmp_path, recover_stale=True).unwrap() as lock:
        assert lock.held


# frob:tests python/sadi/store/lock.py::acquire
def test_unopenable_root_is_lockio(tmp_path: Path) -> None:
    """A missing root yields a LockIo error, not an exception."""
    assert acquire(tmp_path / "missing").is_err


# frob:tests python/sadi/store/lock.py::pid_alive
def test_pid_alive(tmp_path: Path) -> None:
    """Own pid is alive; a reaped child pid is not."""
    assert pid_alive(os.getpid())
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    assert not pid_alive(dead.pid)


# frob:tests python/sadi/store/lock.py::acquire
def test_acquire_and_release_are_logged(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Acquisition and release each emit an INFO log record."""
    with caplog.at_level("INFO", logger="sadi.store.lock"):
        acquire(tmp_path).unwrap().release()
    text = " ".join(r.getMessage() for r in caplog.records)
    assert "acquired" in text
    assert "released" in text


# frob:ticket 01M6XAY79MWPV07858YAKSBJQ6
# frob:tests python/sadi/store/lock.py::read_holder_pid
def test_read_holder_pid_reads_the_live_holder_and_tolerates_junk(tmp_path: Path) -> None:
    """The recorded pid is readable without locking; missing or garbled files give None."""
    path = tmp_path / LOCK_FILENAME
    assert read_holder_pid(path) is None
    with acquire(tmp_path).unwrap():
        assert read_holder_pid(path) == os.getpid()
    path.write_text("pid=notanumber clean", encoding="ascii")
    assert read_holder_pid(path) is None
    path.write_text("nothing useful here", encoding="ascii")
    assert read_holder_pid(path) is None
    path.write_text("host=x pid=4242 other", encoding="ascii")
    assert read_holder_pid(path) == 4242
