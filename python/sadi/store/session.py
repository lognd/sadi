"""Versioned session dirs (data-safety section 8): O_EXCL create, lock, resume, read-only open.

Nothing here ever deletes, truncates or reuses a session directory. Resume creates a new
version directory with a parent link; read-only open performs no write of any kind.
"""

# frob:ticket 01M6W7R1VQHABR51SH64668M06
# frob:ticket 01M6WEM3SYPM2QHFE59YHPNBM1
# frob:ticket 01M6WFZFBK0KYAGBM1CD5GGH60
from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict
from typani import Err, Ok, Result

from sadi.logging_setup import get_logger
from sadi.store.durable import DurableError, DurableIo, create_exclusive, fsync_dir, fsync_file
from sadi.store.failpoints import failpoint
from sadi.store.lock import DataRootLock, LockError, acquire
from sadi.store.manifest import (
    Manifest,
    ManifestInvalid,
    PluginWarning,
    SessionPluginRef,
    plugin_warnings,
    read_manifest,
    write_manifest,
)
from sadi.store.names import sanitize_name
from sadi.store.wal import ScanReport, WalError, WalReader

_log = get_logger(__name__)

SESSIONS_DIRNAME = "sessions"
LOCK_NAME = "lock"
SUBDIRS = ("wal", "snapshots", "exports")
MAX_VERSION = 999
_DIR_RE = re.compile(r"^(?P<family>.+)\.v(?P<ver>\d{3})$")
_SLUG_RE = re.compile(r"[^a-z0-9-]+")
_SLUG_MAX_LEN = 32
_IS_WIN = sys.platform == "win32"


class SessionError(BaseModel):
    """Base of all session failures; `hint` is shown in the UI."""

    model_config = ConfigDict(frozen=True)
    hint: str = ""


class SessionIo(SessionError):
    """A durable or OS operation failed underneath a session operation."""

    error: DurableError


class TooManyVersions(SessionError):
    """All 999 version numbers of the family are taken."""

    family: str
    hint: str = "Start a new session family."


class Locked(SessionError):
    """The session lock is held by another live process (never stolen)."""

    path: Path
    pid_hint: str = ""
    holder_alive: bool | None = None
    hint: str = "Another process has this session open for writing."


class RootLockFailed(SessionError):
    """The data-root lock was not taken: `error` is LockHeld, LockStale or LockIo."""

    error: LockError


class ParentCorrupt(SessionError):
    """The parent WAL is corrupt; writable resume is refused (section 5.4)."""

    parent: Path
    error: WalError


class ParentIncomplete(SessionError):
    """The parent directory has no WAL to resume from (state `incomplete`)."""

    parent: Path
    hint: str = "Nothing to resume; start a new session instead."


class BadSessionName(SessionError):
    """A directory name does not match `<family>.vNNN`."""

    name: str


class NotASession(SessionError):
    """The path is not an existing directory."""

    path: Path


class SessionMeta(BaseModel):
    """Caller-supplied identity of a new session family."""

    model_config = ConfigDict(frozen=True)
    slug: str = "session"
    lab_module: str = ""
    specimen: dict[str, str] = {}
    plugins: tuple[SessionPluginRef, ...] = ()


def _io(exc: OSError, path: Path) -> SessionIo:
    """Wrap an OSError as SessionIo."""
    return SessionIo(error=DurableIo(errno=exc.errno or 5, path=path))


def _slug(raw: str) -> str:
    """Normalise a slug to <=32 portable chars (lowercase, no reserved names), default `session`."""
    # frob:ticket ~9J7TDEC
    base = _SLUG_RE.sub("-", raw.lower()).strip("-")[:32] or "session"
    return sanitize_name(base, max_len=_SLUG_MAX_LEN)


def proc_start_token(pid: int) -> str | None:
    """Return an opaque process start-time token (pid-reuse guard) or None if unknown/gone."""
    try:
        if sys.platform.startswith("linux"):
            stat = Path(f"/proc/{pid}/stat").read_text()
            return stat.rsplit(")", 1)[1].split()[19]
        if sys.platform == "darwin":
            out = subprocess.run(
                ["ps", "-o", "lstart=", "-p", str(pid)],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            ).stdout.strip()
            return out or None
        if _IS_WIN:
            import ctypes  # noqa: PLC0415 - platform-specific
            from ctypes import wintypes  # noqa: PLC0415

            k32 = ctypes.windll.kernel32
            k32.OpenProcess.restype = wintypes.HANDLE
            handle = k32.OpenProcess(0x1000, False, pid)
            if not handle:
                return None
            try:
                times = [wintypes.FILETIME() for _ in range(4)]
                if not k32.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
                    return None
                return str((times[0].dwHighDateTime << 32) | times[0].dwLowDateTime)
            finally:
                k32.CloseHandle(handle)
    except (OSError, IndexError, subprocess.SubprocessError):
        return None
    return None


def _lock_line() -> bytes:
    """Build the human/diagnostic holder line for the lock file."""
    pid = os.getpid()
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    token = proc_start_token(pid) or "unknown"
    host = _SLUG_RE.sub("-", socket.gethostname().lower()) or "host"
    return f"pid={pid} start={token.replace(' ', '_')} host={host} started={now}\n".encode("ascii")


def _try_os_lock(fd: int) -> bool:
    """Take the process-scoped exclusive non-blocking OS lock on `fd`; False if held elsewhere."""
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


def _release_os_lock(fd: int) -> None:
    """Release the OS lock and close the fd (the lock file itself is never deleted)."""
    try:
        if _IS_WIN:
            import msvcrt  # noqa: PLC0415

            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)  # type: ignore[attr-defined]
    except OSError as exc:
        _log.warning("unlock failed: %s", exc)
    finally:
        os.close(fd)


def read_lock_holder(session_dir: Path) -> tuple[str, bool | None]:
    """Read the last lock line (read-only) and judge liveness by pid plus start-time token."""
    try:
        text = (session_dir / LOCK_NAME).read_text(encoding="ascii", errors="replace")
    except OSError:
        return ("", None)
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return ("", None)
    last = lines[-1]
    fields = dict(p.split("=", 1) for p in last.split() if "=" in p)
    try:
        pid = int(fields["pid"])
    except (KeyError, ValueError):
        return (last, None)
    token = proc_start_token(pid)
    recorded = fields.get("start", "unknown")
    if token is None:
        return (last, False)
    if recorded == "unknown":
        return (last, None)
    return (last, token.replace(" ", "_") == recorded)


def probe_lock(session_dir: Path) -> Result[None, Locked]:
    """Check without mutating whether a live writer holds the lock; Ok means it is free."""
    path = session_dir / LOCK_NAME
    try:
        fd = os.open(path, os.O_RDWR | getattr(os, "O_BINARY", 0))
    except FileNotFoundError:
        return Ok(None)
    except OSError as exc:
        _log.error("lock probe open %s failed: %s", path, exc)
        return Ok(None)
    try:
        if _try_os_lock(fd):
            _release_os_lock_keep(fd)
            return Ok(None)
    finally:
        os.close(fd)
    hint, alive = read_lock_holder(session_dir)
    _log.warning("session %s is locked (%s)", session_dir, hint)
    return Err(Locked(path=path, pid_hint=hint, holder_alive=alive))


def _release_os_lock_keep(fd: int) -> None:
    """Unlock `fd` without closing it (the caller closes)."""
    if _IS_WIN:
        import msvcrt  # noqa: PLC0415

        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)  # type: ignore[attr-defined]
    else:
        import fcntl  # noqa: PLC0415

        fcntl.flock(fd, fcntl.LOCK_UN)


@dataclass
class SessionHandle:
    """A writable session version: owns the lock fd and its current manifest."""

    path: Path
    manifest: Manifest
    _lock_fd: int | None = field(default=None, repr=False)
    _root_lock: DataRootLock | None = field(default=None, repr=False)

    def close(self, state: str = "closed") -> Result[None, SessionError]:
        """Write the closed manifest atomically, then release both locks; idempotent."""
        if self._lock_fd is None:
            return Ok(None)
        updated = self.manifest.model_copy(update={"state": state, "closed": datetime.now(UTC)})
        written = write_manifest(self.path, updated)
        _release_os_lock(self._lock_fd)
        self._lock_fd = None
        if self._root_lock is not None:
            self._root_lock.release()
            self._root_lock = None
        if written.is_err:
            return Err(SessionIo(error=written.danger_err))
        object.__setattr__(self, "manifest", updated)
        _log.info("session closed: %s", self.path)
        return Ok(None)


@dataclass(frozen=True)
class ReadOnlySession:
    """A read-only view of a session: never mutates anything on disk."""

    path: Path
    manifest: Manifest | None
    manifest_error: ManifestInvalid | None
    scan: ScanReport | None
    scan_error: WalError | None
    lock_holder: str
    holder_alive: bool | None
    manifest_stale: bool
    plugin_warnings: tuple[PluginWarning, ...] = ()


def _take_version(
    sessions: Path, family: str, start: int
) -> Result[tuple[Path, int], SessionError]:
    """mkdir `<family>.vNNN` exclusively from `start` upward; never reuse a taken name."""
    for ver in range(start, MAX_VERSION + 1):
        path = sessions / f"{family}.v{ver:03d}"
        try:
            failpoint("session.mkdir.before")
            os.mkdir(path)
        except FileExistsError:
            _log.info("version %s taken, trying next", path.name)
            continue
        except OSError as exc:
            _log.error("mkdir %s failed: %s", path, exc)
            return Err(_io(exc, path))
        _log.info("created session dir %s", path)
        return Ok((path, ver))
    _log.error("family %s exhausted all %d versions", family, MAX_VERSION)
    return Err(TooManyVersions(family=family))


def _init_dir(path: Path, manifest: Manifest) -> Result[SessionHandle, SessionError]:
    """Create subdirs, take the lock, write the manifest and fsync the directory entries."""
    try:
        for sub in SUBDIRS:
            os.mkdir(path / sub)
    except OSError as exc:
        _log.error("subdir create in %s failed: %s", path, exc)
        return Err(_io(exc, path))
    created = create_exclusive(path / LOCK_NAME)
    if created.is_err:
        return Err(SessionIo(error=created.danger_err))
    fd = created.danger_ok
    if not _try_os_lock(fd):
        os.close(fd)
        return Err(Locked(path=path / LOCK_NAME))
    try:
        failpoint("session.lock.after")
        os.write(fd, _lock_line())
        synced = fsync_file(fd)
    except OSError as exc:
        _release_os_lock(fd)
        return Err(_io(exc, path))
    if synced.is_err:
        _release_os_lock(fd)
        return Err(SessionIo(error=synced.danger_err))
    written = write_manifest(path, manifest)
    if written.is_err:
        _release_os_lock(fd)
        return Err(SessionIo(error=written.danger_err))
    for d in (path, path.parent):
        r = fsync_dir(d)
        if r.is_err:
            _release_os_lock(fd)
            return Err(SessionIo(error=r.danger_err))
    _log.info("session initialised: %s", path)
    return Ok(SessionHandle(path=path, manifest=manifest, _lock_fd=fd))


def _take_root_lock(root: Path, recover_stale: bool) -> Result[DataRootLock, SessionError]:
    """Acquire the data-root lock, mapping LockHeld/LockStale/LockIo to RootLockFailed."""
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return Err(_io(exc, root))
    got = acquire(root, recover_stale=recover_stale)
    if got.is_err:
        err = got.danger_err
        _log.warning("data-root lock refused for %s: %s", root, type(err).__name__)
        return Err(RootLockFailed(error=err, hint=err.hint))
    return Ok(got.danger_ok)


def _attach_root_lock(
    built: Result[SessionHandle, SessionError], lock: DataRootLock
) -> Result[SessionHandle, SessionError]:
    """Hand `lock` to the new handle, or release it if the session was not created."""
    if built.is_err:
        lock.release()
        return built
    built.danger_ok._root_lock = lock  # noqa: SLF001 - same module
    return built


def create_session(
    root: Path,
    meta: SessionMeta,
    now: datetime | None = None,
    *,
    recover_stale: bool = False,
) -> Result[SessionHandle, SessionError]:
    """Lock `root`, then create a new family at v001 (or next free) under `<root>/sessions`.

    A stale data-root lock is reported as RootLockFailed unless the user passes `recover_stale`.
    """
    locked = _take_root_lock(root, recover_stale)
    if locked.is_err:
        return Err(locked.danger_err)
    return _attach_root_lock(_create_locked(root, meta, now), locked.danger_ok)


def _create_locked(
    root: Path, meta: SessionMeta, now: datetime | None
) -> Result[SessionHandle, SessionError]:
    """Create the session dir once the data-root lock is held."""
    when = now or datetime.now(UTC)
    sessions = root / SESSIONS_DIRNAME
    try:
        sessions.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return Err(_io(exc, sessions))
    family = f"{when.strftime('%Y%m%dT%H%M%SZ')}-{_slug(meta.slug)}"
    taken = _take_version(sessions, family, 1)
    if taken.is_err:
        return Err(taken.danger_err)
    path, ver = taken.danger_ok
    manifest = Manifest(
        session_uuid=str(uuid.uuid4()),
        dir_name=path.name,
        family=family,
        version=ver,
        created=when,
        lab_module=meta.lab_module,
        specimen=meta.specimen,
        plugins=meta.plugins,
    )
    return _init_dir(path, manifest)


def resume_session(
    parent_dir: Path,
    *,
    recover_stale: bool = False,
    plugins: Sequence[SessionPluginRef] | None = None,
) -> Result[SessionHandle, SessionError]:
    """Lock the data root, then create the next version dir linked to `parent_dir`.

    The parent is never modified; a stale data-root lock needs explicit `recover_stale`.
    `plugins` records provenance for the new version; None inherits the parent's list.
    """
    m = _DIR_RE.match(parent_dir.name)
    if m is None:
        return Err(BadSessionName(name=parent_dir.name))
    if not parent_dir.is_dir():
        return Err(NotASession(path=parent_dir))
    locked = _take_root_lock(parent_dir.parent.parent, recover_stale)
    if locked.is_err:
        return Err(locked.danger_err)
    return _attach_root_lock(_resume_locked(parent_dir, m, plugins), locked.danger_ok)


def _resume_locked(
    parent_dir: Path, m: re.Match[str], plugins: Sequence[SessionPluginRef] | None = None
) -> Result[SessionHandle, SessionError]:
    """Resume once the data-root lock is held."""
    locked = probe_lock(parent_dir)
    if locked.is_err:
        return Err(locked.danger_err)
    if not (parent_dir / "wal").is_dir():
        return Err(ParentIncomplete(parent=parent_dir))
    scan = WalReader.scan(parent_dir / "wal")
    if scan.is_err:
        _log.error("refusing resume of %s: corrupt or incomplete WAL", parent_dir)
        return Err(ParentCorrupt(parent=parent_dir, error=scan.danger_err))
    report = scan.danger_ok
    family = m.group("family")
    now = datetime.now(UTC)
    taken = _take_version(parent_dir.parent, family, int(m.group("ver")) + 1)
    if taken.is_err:
        return Err(taken.danger_err)
    path, ver = taken.danger_ok
    pm = read_manifest(parent_dir)
    pmf = pm.danger_ok if pm.is_ok else None
    manifest = Manifest(
        session_uuid=str(uuid.uuid4()),
        dir_name=path.name,
        family=family,
        version=ver,
        parent=parent_dir.name,
        parent_last_seq=report.last_seq,
        created=now,
        lab_module=pmf.lab_module if pmf is not None else "",
        specimen=pmf.specimen if pmf is not None else {},
        plugins=tuple(plugins) if plugins is not None else (pmf.plugins if pmf is not None else ()),
    )
    _log.info("resuming %s as %s (parent_last_seq=%s)", parent_dir.name, path.name, report.last_seq)
    return _init_dir(path, manifest)


def open_readonly(
    session_dir: Path, available_plugins: Mapping[str, str] | None = None
) -> Result[ReadOnlySession, SessionError]:
    """Open for review: reads manifest, lock text and WAL only; writes nothing, repairs nothing.

    With `available_plugins` (id -> version), missing or differing plugins only warn.
    """
    if not session_dir.is_dir():
        return Err(NotASession(path=session_dir))
    mf = read_manifest(session_dir)
    manifest = mf.danger_ok if mf.is_ok else None
    manifest_error = mf.danger_err if mf.is_err else None
    scan: ScanReport | None = None
    scan_error: WalError | None = None
    if (session_dir / "wal").is_dir():
        res = WalReader.scan(session_dir / "wal")
        if res.is_ok:
            scan = res.danger_ok
        else:
            scan_error = res.danger_err
    holder, alive = read_lock_holder(session_dir)
    stale = manifest is None or (scan is not None and manifest.last_seq != scan.last_seq)
    if stale:
        _log.info("manifest of %s is missing or stale (not repaired: read-only)", session_dir)
    warnings = (
        plugin_warnings(manifest.plugins, available_plugins)
        if manifest is not None and available_plugins is not None
        else ()
    )
    return Ok(
        ReadOnlySession(
            path=session_dir,
            manifest=manifest,
            manifest_error=manifest_error,
            scan=scan,
            scan_error=scan_error,
            lock_holder=holder,
            holder_alive=alive,
            manifest_stale=stale,
            plugin_warnings=warnings,
        )
    )
