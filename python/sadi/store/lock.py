"""Exclusive OS-level lock on the data root so two sadi processes never share it."""

# frob:ticket 01M6WEFG72EDSKCAY9AX8YD1SA
from __future__ import annotations

import os
import socket
import sys
from pathlib import Path
from types import TracebackType

from pydantic import BaseModel, ConfigDict
from typani import Err, Ok, Result

from sadi.logging_setup import get_logger

_log = get_logger(__name__)

LOCK_FILENAME = ".sadi-data.lock"
_IS_WIN = sys.platform == "win32"


class LockError(BaseModel):
    """Base of all data-root lock failures; `hint` is shown in the UI."""

    model_config = ConfigDict(frozen=True)
    path: Path
    hint: str = ""


class LockHeld(LockError):
    """Another live process holds the lock; `pid` is its recorded pid (None if unreadable)."""

    pid: int | None = None


class LockStale(LockError):
    """The OS lock is free but the file records a dead holder; needs explicit recovery."""

    pid: int
    hint: str = "A previous sadi process exited uncleanly; reacquire with recover_stale=True."


class LockIo(LockError):
    """An OS call failed with `errno`."""

    errno: int | None = None


def _os_lock(fd: int) -> bool:
    """Take the non-blocking exclusive OS lock on `fd`; False if held elsewhere."""
    try:
        if _IS_WIN:
            import msvcrt  # noqa: PLC0415 - platform-specific

            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)  # type: ignore[attr-defined]
        else:
            import fcntl  # noqa: PLC0415 - platform-specific

            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def _os_unlock(fd: int) -> None:
    """Release the OS lock on `fd` (errors are logged, never raised)."""
    try:
        if _IS_WIN:
            import msvcrt  # noqa: PLC0415

            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)  # type: ignore[attr-defined]
        else:
            import fcntl  # noqa: PLC0415

            fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError as exc:
        _log.warning("unlock failed: %s", exc)


def pid_alive(pid: int) -> bool:
    """Best-effort liveness check of `pid` (signal 0 on POSIX, OpenProcess on Windows)."""
    if _IS_WIN:
        import ctypes  # noqa: PLC0415

        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # type: ignore[attr-defined]
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)  # type: ignore[attr-defined]
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def read_holder_pid(path: Path) -> int | None:
    """Read the pid recorded in the lock file (read-only); None if absent or unparsable."""
    try:
        text = path.read_text(encoding="ascii", errors="replace")
    except OSError:
        return None
    for token in text.split():
        if token.startswith("pid="):
            try:
                return int(token[4:])
            except ValueError:
                return None
    return None


class DataRootLock:
    """A held data-root lock; release it explicitly or use it as a context manager."""

    def __init__(self, path: Path, fd: int) -> None:
        """Wrap an already-locked `fd` for lock file `path`."""
        self.path = path
        self._fd: int | None = fd

    @property
    def held(self) -> bool:
        """True until `release` is called."""
        return self._fd is not None

    def release(self) -> None:
        """Mark the file clean, unlock and close; idempotent. The file is never deleted."""
        if self._fd is None:
            return
        fd, self._fd = self._fd, None
        try:
            os.ftruncate(fd, 0)
        except OSError as exc:
            _log.warning("clearing lock file %s failed: %s", self.path, exc)
        _os_unlock(fd)
        os.close(fd)
        _log.info("released data-root lock %s", self.path)

    def __enter__(self) -> DataRootLock:
        """Return self; the lock is already held."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Release on scope exit."""
        self.release()


def acquire(root: Path, *, recover_stale: bool = False) -> Result[DataRootLock, LockError]:
    """Lock `root`; Err(LockHeld) if a live process holds it, Err(LockStale) if a dead one left it.

    Nothing under `root` other than the lock file is touched. A stale lock is only taken over
    when the caller passes `recover_stale=True` (an explicit user action).
    """
    path = root / LOCK_FILENAME
    try:
        fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0), 0o644)
    except OSError as exc:
        _log.error("cannot open lock file %s: %s", path, exc)
        return Err(LockIo(path=path, errno=exc.errno, hint=str(exc)))
    if not _os_lock(fd):
        os.close(fd)
        pid = read_holder_pid(path)
        _log.warning("data root %s is locked by pid %s", root, pid)
        return Err(
            LockHeld(
                path=path,
                pid=pid,
                hint=f"Another sadi process (pid {pid}) is using this data folder.",
            )
        )
    prior = read_holder_pid(path)
    if prior is not None and not recover_stale:
        _os_unlock(fd)
        os.close(fd)
        _log.warning("data root %s has a stale lock from pid %s", root, prior)
        return Err(LockStale(path=path, pid=prior))
    if prior is not None:
        _log.warning("recovering stale lock %s from pid %s by explicit request", path, prior)
    try:
        os.ftruncate(fd, 0)
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, f"pid={os.getpid()} host={socket.gethostname()}\n".encode("ascii", "replace"))
        os.fsync(fd)
    except OSError as exc:
        _os_unlock(fd)
        os.close(fd)
        _log.error("cannot record holder in %s: %s", path, exc)
        return Err(LockIo(path=path, errno=exc.errno, hint=str(exc)))
    _log.info("acquired data-root lock %s", path)
    return Ok(DataRootLock(path, fd))
