"""Cross-OS durability primitives (data-safety section 10): fsync, dir fsync, create, replace."""

from __future__ import annotations

import ctypes
import errno
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ConfigDict
from typani import Err, Ok, Result

from sadi.logging_setup import get_logger
from sadi.store.failpoints import failpoint

_log = get_logger(__name__)

T = TypeVar("T")

SHARING_RETRY_TOTAL_S = 5.0
SHARING_RETRY_FIRST_S = 0.010
SHARING_RETRY_CAP_S = 0.5
SHARING_WINERRORS = (5, 32)

_IS_WIN = sys.platform == "win32"
_IS_MAC = sys.platform == "darwin"
_MOVEFILE_REPLACE_EXISTING = 0x1
_MOVEFILE_WRITE_THROUGH = 0x8
_RENAME_NOREPLACE = 1
_AT_FDCWD = -100
_WIN_EXISTS_ERRORS = (80, 183)  # ERROR_FILE_EXISTS, ERROR_ALREADY_EXISTS
_GENERIC_WRITE = 0x40000000
_FILE_SHARE_ALL = 0x7  # READ | WRITE | DELETE
_OPEN_EXISTING = 3
_FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
_INVALID_HANDLE = ctypes.c_void_p(-1).value

# Indirection points so tests can run the retry logic without real waiting.
_sleep = time.sleep
_monotonic = time.monotonic

_state = {"downgraded": False}


class DurableError(BaseModel):
    """Base of all durability failures; `hint` is shown in the UI."""

    model_config = ConfigDict(frozen=True)
    hint: str = ""


class DurableIo(DurableError):
    """An OS call failed with `errno` (path is None for fd-based calls)."""

    errno: int
    path: Path | None = None


class DurableSharingViolation(DurableError):
    """Windows sharing violation persisted for `attempts` tries (antivirus, indexer)."""

    path: Path
    attempts: int
    hint: str = "Exclude the data folder from real-time antivirus scanning and retry."


class DurableCrossDevice(DurableError):
    """tmp and dst are not in the same directory, so replace would not be atomic."""

    tmp: Path
    dst: Path


class DurableUnsupported(DurableError):
    """The operation is not supported here."""

    op: str
    reason: str


class DurableExists(DurableError):
    """The target already exists and was not touched (never overwrite)."""

    path: Path
    hint: str = "A file with this name already exists; nothing was changed."


def durability_downgraded() -> bool:
    """Return True once F_FULLFSYNC fell back to plain fsync (macOS, exFAT and similar)."""
    return _state["downgraded"]


def _io(exc: OSError, path: Path | None) -> DurableIo:
    """Wrap an OSError as a DurableIo with a hint."""
    code = exc.errno or errno.EIO
    hint = "The disk is full." if code == errno.ENOSPC else "A disk error occurred; see the log."
    return DurableIo(errno=code, path=path, hint=hint)


def _flush_fd(fd: int) -> None:
    """Flush one fd: F_FULLFSYNC on macOS with a once-logged fallback, plain os.fsync elsewhere."""
    if _IS_MAC:
        import fcntl  # noqa: PLC0415 - platform-specific

        try:
            fcntl.fcntl(fd, fcntl.F_FULLFSYNC)
            return
        except OSError as exc:
            if exc.errno not in (errno.ENOTSUP, errno.EINVAL):
                raise
            if not _state["downgraded"]:
                _log.warning("F_FULLFSYNC unsupported (%s); falling back to fsync", exc)
            _state["downgraded"] = True
    os.fsync(fd)


def fsync_file(fd: int) -> Result[None, DurableError]:
    """Flush file data and metadata of `fd` to stable storage (never fdatasync)."""
    try:
        failpoint("durable.fsync_file")
        _flush_fd(fd)
    except OSError as exc:
        _log.error("fsync_file(fd=%d) failed: %s", fd, exc)
        return Err(_io(exc, None))
    _log.debug("fsync_file(fd=%d) ok", fd)
    return Ok(None)


def _win_flush_dir(path: Path) -> None:
    """Flush a Windows dir: CreateFileW(BACKUP_SEMANTICS) + FlushFileBuffers (UNVERIFIED)."""
    from ctypes import wintypes  # noqa: PLC0415 - Windows-only use

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)  # ty: ignore[unresolved-attribute]
    k32.CreateFileW.restype = wintypes.HANDLE
    k32.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    k32.FlushFileBuffers.argtypes = [wintypes.HANDLE]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = k32.CreateFileW(
        str(path),
        _GENERIC_WRITE,
        _FILE_SHARE_ALL,
        None,
        _OPEN_EXISTING,
        _FILE_FLAG_BACKUP_SEMANTICS,
        None,
    )
    if handle in (None, _INVALID_HANDLE):
        raise ctypes.WinError(ctypes.get_last_error())  # ty: ignore[unresolved-attribute]
    try:
        failpoint("durable.fsync_file")
        if not k32.FlushFileBuffers(handle):
            raise ctypes.WinError(ctypes.get_last_error())  # ty: ignore[unresolved-attribute]
    finally:
        k32.CloseHandle(handle)


def fsync_dir(path: Path) -> Result[None, DurableError]:
    """Flush a directory entry table (ctypes FlushFileBuffers on Windows, UNVERIFIED there)."""
    if _IS_WIN:
        try:
            _win_flush_dir(path)
        except OSError as exc:
            _log.error("fsync_dir %s failed (windows): %s", path, exc)
            return Err(_io(exc, path))
        _log.debug("fsync_dir(%s) ok (windows)", path)
        return Ok(None)
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError as exc:
        _log.error("fsync_dir open %s failed: %s", path, exc)
        return Err(_io(exc, path))
    try:
        failpoint("durable.fsync_file")
        _flush_fd(fd)
    except OSError as exc:
        _log.error("fsync_dir %s failed: %s", path, exc)
        return Err(_io(exc, path))
    finally:
        os.close(fd)
    _log.debug("fsync_dir(%s) ok", path)
    return Ok(None)


def _retry_sharing(op: Callable[[], T], path: Path, label: str) -> Result[T, DurableError]:
    """Run `op`, retrying Windows sharing violations with capped backoff; map errors."""
    attempts = 0
    delay = SHARING_RETRY_FIRST_S
    start = _monotonic()
    while True:
        try:
            return Ok(op())
        except FileExistsError:
            _log.warning("%s: %s already exists; refusing to overwrite", label, path)
            return Err(DurableExists(path=path))
        except PermissionError as exc:
            if getattr(exc, "winerror", None) not in SHARING_WINERRORS:
                _log.error("%s %s failed: %s", label, path, exc)
                return Err(_io(exc, path))
            attempts += 1
            if _monotonic() - start + delay > SHARING_RETRY_TOTAL_S:
                _log.error(
                    "%s %s: sharing violation persisted after %d attempts", label, path, attempts
                )
                return Err(DurableSharingViolation(path=path, attempts=attempts))
            _log.warning(
                "%s %s: sharing violation, retry %d in %.0f ms", label, path, attempts, delay * 1000
            )
            _sleep(delay)
            delay = min(delay * 2, SHARING_RETRY_CAP_S)
        except OSError as exc:
            _log.error("%s %s failed: %s", label, path, exc)
            return Err(_io(exc, path))


def create_exclusive(path: Path) -> Result[int, DurableError]:
    """Create `path` with O_EXCL (CREATE_NEW) and return a write fd; never overwrites."""
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_BINARY", 0)
    )

    def _open() -> int:
        failpoint("durable.rename")
        return os.open(path, flags, 0o644)

    result = _retry_sharing(_open, path, "create_exclusive")
    if result.is_ok:
        _log.info("created %s exclusively", path)
    return result


def _replace_os(tmp: Path, dst: Path) -> None:
    """Atomic replace via os.replace, or MoveFileExW with WRITE_THROUGH on Windows."""
    failpoint("durable.rename")
    if not _IS_WIN:
        os.replace(tmp, dst)
        return
    move = ctypes.windll.kernel32.MoveFileExW
    if not move(str(tmp), str(dst), _MOVEFILE_REPLACE_EXISTING | _MOVEFILE_WRITE_THROUGH):
        raise ctypes.WinError(ctypes.get_last_error())


def atomic_replace(tmp: Path, dst: Path) -> Result[None, DurableError]:
    """Fsync `tmp`, rename it over `dst`, fsync the directory; `dst` survives any failure."""
    if tmp.parent.resolve() != dst.parent.resolve():
        _log.error("atomic_replace: %s and %s are in different directories", tmp, dst)
        return Err(
            DurableCrossDevice(tmp=tmp, dst=dst, hint="Programmer error: tmp must sit next to dst.")
        )
    try:
        fd = os.open(tmp, os.O_RDWR | getattr(os, "O_BINARY", 0))
    except OSError as exc:
        _log.error("atomic_replace: cannot open %s: %s", tmp, exc)
        return Err(_io(exc, tmp))
    try:
        synced = fsync_file(fd)
    finally:
        os.close(fd)
    if synced.is_err:
        return synced
    renamed = _retry_sharing(lambda: _replace_os(tmp, dst), dst, "atomic_replace")
    if renamed.is_err:
        return renamed
    _log.info("replaced %s with %s", dst, tmp)
    return fsync_dir(dst.parent)


def _renameat2_noreplace(src: Path, dst: Path) -> bool:
    """Try renameat2(RENAME_NOREPLACE); False when the kernel or filesystem lacks it."""
    libc = ctypes.CDLL(None, use_errno=True)
    fn = getattr(libc, "renameat2", None)
    if fn is None:
        return False
    rc = fn(_AT_FDCWD, os.fsencode(src), _AT_FDCWD, os.fsencode(dst), _RENAME_NOREPLACE)
    if rc == 0:
        return True
    code = ctypes.get_errno()
    if code in (errno.ENOSYS, errno.EINVAL, errno.ENOTSUP):
        _log.warning("renameat2 unsupported (%s); using link+unlink", os.strerror(code))
        return False
    if code == errno.EEXIST:
        raise FileExistsError(code, os.strerror(code), str(dst))
    raise OSError(code, os.strerror(code), str(dst))


def _link_unlink(src: Path, dst: Path) -> None:
    """No-replace rename via hard link then unlink; os.link fails if `dst` exists."""
    os.link(src, dst)
    try:
        os.unlink(src)
    except OSError:
        _log.error("link+unlink: %s linked to %s but source unlink failed", src, dst)
        raise


def _rename_noreplace_os(src: Path, dst: Path) -> None:
    """Rename without replacing `dst`: renameat2, MoveFileExW (Windows), else link+unlink."""
    failpoint("durable.rename")
    if _IS_WIN:
        move = ctypes.windll.kernel32.MoveFileExW
        if not move(str(src), str(dst), _MOVEFILE_WRITE_THROUGH):
            code = ctypes.get_last_error()
            if code in _WIN_EXISTS_ERRORS:
                raise FileExistsError(errno.EEXIST, "destination exists", str(dst))
            raise ctypes.WinError(code)
        return
    if sys.platform.startswith("linux") and _renameat2_noreplace(src, dst):
        return
    _link_unlink(src, dst)


def rename_noreplace(src: Path, dst: Path) -> Result[None, DurableError]:
    """Rename `src` to `dst` without ever replacing `dst`, then fsync the directories."""
    renamed = _retry_sharing(lambda: _rename_noreplace_os(src, dst), dst, "rename_noreplace")
    if renamed.is_err:
        return renamed
    _log.info("renamed %s to %s without replace", src, dst)
    synced = fsync_dir(dst.parent)
    if synced.is_err or src.parent == dst.parent:
        return synced
    return fsync_dir(src.parent)
