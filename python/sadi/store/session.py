"""Versioned session dirs (data-safety section 8): O_EXCL create, lock, resume, read-only open.

Nothing here ever deletes, truncates or reuses a session directory. Resume creates a new
version directory with a parent link; read-only open performs no write of any kind.
"""

# frob:ticket 01M6W7R1VQHABR51SH64668M06
# frob:ticket 01M6WEM3SYPM2QHFE59YHPNBM1
# frob:ticket 01M6WFZFBK0KYAGBM1CD5GGH60
# frob:ticket 01M6W7R3XY1B0BF689RX3H80G2
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
from typani import Err, Ok, Result, propagate

from sadi.logging_setup import get_logger
from sadi.store.durable import DurableError, DurableIo, create_exclusive, fsync_dir, fsync_file
from sadi.store.failpoints import failpoint
from sadi.store.lock import DataRootLock, LockError, acquire, try_lock_fd, unlock_fd
from sadi.store.manifest import (
    Manifest,
    ManifestInvalid,
    PluginWarning,
    SessionPluginRef,
    plugin_warnings,
    read_manifest,
    write_manifest,
)
from sadi.store.names import ascii_fold, sanitize_name
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


class ProvenanceMismatch(SessionError):
    """A resume asked for a different data mode (real vs synthetic) than the parent session."""

    # frob:ticket 01M71SYG3H3X7GJT21TE6MY8YC
    parent: Path
    parent_synthetic: bool
    hint: str = "Real and synthetic data are never mixed; start a new session in the same mode."


#: Name of the immutable marker file that makes a session directory permanently synthetic.
SYNTHETIC_MARKER = "SYNTHETIC"
_SYNTHETIC_MARKER_TEXT = b"SYNTHETIC DATA: simulated copper specimen, not a physical measurement.\n"


def session_is_synthetic(session_dir: Path) -> bool:
    """True when the SYNTHETIC marker OR the manifest says synthetic (losing one never relabels)."""
    # frob:ticket 01M71SYG3H3X7GJT21TE6MY8YC
    # frob:ticket 01M720QDHPFPD9CNEADS1CA9V6
    if (session_dir / SYNTHETIC_MARKER).is_file():
        return True
    mf = read_manifest(session_dir)
    if mf.is_err:
        _log.warning("session %s: manifest unreadable while checking provenance", session_dir.name)
        return False
    if mf.danger_ok is not None and mf.danger_ok.synthetic:
        _log.warning("session %s: SYNTHETIC marker missing but manifest says synthetic", session_dir.name)
        return True
    return False


def session_provenance_unknown(session_dir: Path) -> bool:
    """True when the manifest flags the session's data origin as unknown (orphan spill import)."""
    # frob:ticket 01M72TJ0CQPCRKAW2EWSFP9Y8Z
    mf = read_manifest(session_dir)
    if mf.is_err or mf.danger_ok is None:
        return False
    return mf.danger_ok.provenance_unknown


def _write_synthetic_marker(path: Path) -> Result[None, SessionError]:
    """Create the SYNTHETIC marker exclusively (never overwritten) and fsync it."""
    # frob:ticket 01M71SYG3H3X7GJT21TE6MY8YC
    created = create_exclusive(path / SYNTHETIC_MARKER)
    if created.is_err:
        return Err(SessionIo(error=created.danger_err))
    fd = created.danger_ok
    try:
        os.write(fd, _SYNTHETIC_MARKER_TEXT)
        synced = fsync_file(fd)
    except OSError as exc:
        return Err(_io(exc, path))
    finally:
        os.close(fd)
    if synced.is_err:
        return Err(SessionIo(error=synced.danger_err))
    _log.warning("session %s marked SYNTHETIC", path.name)
    return Ok(None)


class SessionMeta(BaseModel):
    """Caller-supplied identity of a new session family."""

    model_config = ConfigDict(frozen=True)
    slug: str = "session"
    lab_module: str = ""
    specimen: dict[str, str] = {}
    plugins: tuple[SessionPluginRef, ...] = ()
    synthetic: bool = False  # frob:ticket 01M71SYG3H3X7GJT21TE6MY8YC


def _io(exc: OSError, path: Path) -> SessionIo:
    """Wrap an OSError as SessionIo."""
    return SessionIo(error=DurableIo(errno=exc.errno or 5, path=path))


def _slug(raw: str) -> str:
    """Normalise a slug to <=32 portable chars (lowercase, no reserved names), default `session`."""
    # frob:ticket 01M6WC0KV4VWZ2E3A989J7TDEC
    base = _SLUG_RE.sub("-", ascii_fold(raw).lower()).strip("-")[:32] or "session"
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
    return try_lock_fd(fd)


def _release_os_lock(fd: int) -> None:
    """Release the OS lock and close the fd (the lock file itself is never deleted)."""
    try:
        unlock_fd(fd)
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
    unlock_fd(fd)


@dataclass
class SessionHandle:
    """A writable session version: owns the lock fd and its current manifest."""

    path: Path
    manifest: Manifest
    _lock_fd: int | None = field(default=None, repr=False)
    _root_lock: DataRootLock | None = field(default=None, repr=False)

    def _wal_last_seq(self) -> int | None:
        """Last verified WAL seq for the closing manifest, or the old value if unreadable."""
        scan = WalReader.scan(self.path / "wal") if (self.path / "wal").is_dir() else None
        if scan is None or scan.is_err:
            _log.warning("close of %s: WAL not scannable; last_seq left as %s", self.path.name,
                         self.manifest.last_seq)
            return self.manifest.last_seq
        return scan.danger_ok.last_seq

    @propagate
    def close(self, state: str = "closed") -> Result[None, SessionError]:
        """Write the closed manifest atomically, then release both locks; idempotent."""
        if self._lock_fd is None:
            return Ok(None)
        # frob:ticket 01M71XGK2GSEZ1GM3N3ES7916A
        updated = self.manifest.model_copy(
            update={"state": state, "closed": datetime.now(UTC), "last_seq": self._wal_last_seq()}
        )
        written = write_manifest(self.path, updated)
        _release_os_lock(self._lock_fd)
        self._lock_fd = None
        if self._root_lock is not None:
            self._root_lock.release()
            self._root_lock = None
        written.map_err(lambda e: SessionIo(error=e)).unwrap()
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


def _free_family(sessions: Path, base: str) -> str:
    """Return `base`, or `base-2`, `base-3`... so a new session never joins another family."""
    # frob:ticket 01M71XGK2GSEZ1GM3N3ES7916A
    def used(fam: str) -> bool:
        """True if any version dir of `fam` exists (case-insensitive for portable roots)."""
        prefix = f"{fam}.v".casefold()
        return any(p.name.casefold().startswith(prefix) for p in sessions.iterdir())

    fam, n = base, 1
    while used(fam):
        n += 1
        fam = f"{base}-{n}"
    if n > 1:
        _log.warning("session family %s already exists; using %s", base, fam)
    return fam


@propagate
def _init_dir(path: Path, manifest: Manifest) -> Result[SessionHandle, SessionError]:
    """Create subdirs, take the lock, write the manifest and fsync the directory entries."""
    try:
        for sub in SUBDIRS:
            os.mkdir(path / sub)
    except OSError as exc:
        _log.error("subdir create in %s failed: %s", path, exc)
        return Err(_io(exc, path))
    created = create_exclusive(path / LOCK_NAME)
    fd = created.map_err(lambda e: SessionIo(error=e)).unwrap()
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
    if manifest.synthetic:
        marked = _write_synthetic_marker(path)  # frob:ticket 01M71SYG3H3X7GJT21TE6MY8YC
        if marked.is_err:
            _release_os_lock(fd)
            return Err(marked.danger_err)
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


@propagate
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
    root_lock = locked.unwrap()
    return _attach_root_lock(_create_locked(root, meta, now), root_lock)


def create_session_in_held_root(
    root: Path, meta: SessionMeta, now: datetime | None = None
) -> Result[SessionHandle, SessionError]:
    """Create a session when the caller (the server) already holds the data-root lock.

    The handle owns no root lock; the caller keeps it for its own lifetime.
    """
    return _create_locked(root, meta, now)


@propagate
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
    family = _free_family(sessions, f"{when.strftime('%Y%m%dT%H%M%SZ')}-{_slug(meta.slug)}")
    taken = _take_version(sessions, family, 1)
    path, ver = taken.unwrap()
    manifest = Manifest(
        session_uuid=str(uuid.uuid4()),
        dir_name=path.name,
        family=family,
        version=ver,
        created=when,
        lab_module=meta.lab_module,
        specimen=meta.specimen,
        plugins=meta.plugins,
        synthetic=meta.synthetic,
    )
    return _init_dir(path, manifest)


@propagate
def resume_session(
    parent_dir: Path,
    *,
    recover_stale: bool = False,
    plugins: Sequence[SessionPluginRef] | None = None,
    synthetic: bool | None = None,
) -> Result[SessionHandle, SessionError]:
    """Lock the data root, then create the next version dir linked to `parent_dir`.

    The parent is never modified; a stale data-root lock needs explicit `recover_stale`.
    `plugins` records provenance for the new version; None inherits the parent's list.
    `synthetic` (when given) must equal the parent's mode or ProvenanceMismatch is returned.
    """
    m = _DIR_RE.match(parent_dir.name)
    if m is None:
        return Err(BadSessionName(name=parent_dir.name))
    if not parent_dir.is_dir():
        return Err(NotASession(path=parent_dir))
    locked = _take_root_lock(parent_dir.parent.parent, recover_stale)
    root_lock = locked.unwrap()
    return _attach_root_lock(_resume_locked(parent_dir, m, plugins, synthetic), root_lock)


def resume_session_in_held_root(
    parent_dir: Path,
    *,
    plugins: Sequence[SessionPluginRef] | None = None,
    synthetic: bool | None = None,
) -> Result[SessionHandle, SessionError]:
    """Resume `parent_dir` as a new version when the caller already holds the data-root lock."""
    m = _DIR_RE.match(parent_dir.name)
    if m is None:
        return Err(BadSessionName(name=parent_dir.name))
    if not parent_dir.is_dir():
        return Err(NotASession(path=parent_dir))
    return _resume_locked(parent_dir, m, plugins, synthetic)


@propagate
def _resume_locked(
    parent_dir: Path,
    m: re.Match[str],
    plugins: Sequence[SessionPluginRef] | None = None,
    synthetic: bool | None = None,
) -> Result[SessionHandle, SessionError]:
    """Resume once the data-root lock is held; the child inherits the parent's data mode."""
    parent_synth = session_is_synthetic(parent_dir)  # frob:ticket 01M71SYG3H3X7GJT21TE6MY8YC
    if synthetic is not None and synthetic != parent_synth:
        _log.error("refusing resume of %s: data-mode mismatch", parent_dir.name)
        return Err(ProvenanceMismatch(parent=parent_dir, parent_synthetic=parent_synth))
    locked = probe_lock(parent_dir)
    locked.unwrap()
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
    path, ver = taken.unwrap()
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
        synthetic=parent_synth,
        provenance_unknown=pmf.provenance_unknown if pmf is not None else False,  # frob:ticket 01M72TJ0CQPCRKAW2EWSFP9Y8Z
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
