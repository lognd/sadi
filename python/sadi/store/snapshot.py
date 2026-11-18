"""Atomic snapshot files of derived state and their recovery (data-safety.md section 9.1).

A snapshot is one WAL-framed JSON payload written tmp + fsync + no-replace publish + directory
fsync. Snapshots are derived and losable: recovery verifies the frame CRC and the prefix hash of
the covered WAL prefix, ignores anything that fails (never deleting it) and replays the WAL.
"""

# frob:ticket 01M6W7R2F3KJWQCWEKZK6BT3MG
from __future__ import annotations

import errno
import os
import secrets
import time
from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, ValidationError
from typani import Err, Ok, Result, propagate

from sadi.logging_setup import get_logger
from sadi.store import durable
from sadi.store.durable import DurableError
from sadi.store.failpoints import failpoint
from sadi.store.records import (
    FLAG_JSON,
    MAX_PAYLOAD,
    NewRecord,
    Record,
    RecordType,
    decode_frame,
    encode_frame,
    json_record,
    new_prefix_hash,
    prefix_hash_update,
)
from sadi.store.wal import WalError, WalReader

_log = get_logger(__name__)

SNAPSHOT_DIR = "snapshots"
SNAPSHOT_VERSION = 1
#: Minimum seconds between snapshots that no POINT/EDIT/close forced (data-safety.md 9.1).
SNAPSHOT_MIN_INTERVAL_S = 5.0
SNAPSHOT_FRAME_TYPE = int(RecordType.SNAPSHOT_REF)
_LINK_FALLBACK_ERRNOS = frozenset(
    {errno.EPERM, errno.ENOTSUP, errno.EOPNOTSUPP, errno.EMLINK, errno.ENOSYS, errno.EACCES}
)


class SnapshotError(BaseModel):
    """Base of snapshot failures; `hint` is shown in the UI."""

    model_config = ConfigDict(frozen=True)
    hint: str = ""


class SnapshotIo(SnapshotError):
    """A durability primitive or OS call failed while writing or reading a snapshot."""

    error: DurableError
    hint: str = "A disk error occurred while saving a snapshot; the recording itself is safe."


class SnapshotWal(SnapshotError):
    """The WAL could not be verified, so no snapshot claim can be made about it."""

    error: WalError
    hint: str = "The recording could not be verified; see the log."


class SnapshotAhead(SnapshotError):
    """A snapshot was requested for a seq beyond the verified WAL."""

    covers_seq: int
    last_seq: int | None
    hint: str = "Snapshots may only cover records that are already in the verified log."


class SnapshotTooLarge(SnapshotError):
    """The serialised snapshot exceeds the frame payload limit."""

    size: int
    hint: str = "The derived state is too large to snapshot; replay from the log still works."


class SnapshotV1(BaseModel):
    """Snapshot payload: replay state after applying WAL records up to `covers_seq`."""

    model_config = ConfigDict(frozen=True, extra="allow")
    v: int = SNAPSHOT_VERSION
    covers_seq: int
    prefix_hash: str
    code_version: dict[str, Any] = {}
    lab_module: str = ""
    state: dict[str, Any]
    # frob:ticket 01M72YGM028WQQGWVSDX4GTJZ5
    notes: list[str] | None = None  # JSON NOTE payloads up to covers_seq; None on old snapshots


class SnapshotRef(BaseModel):
    """SNAPSHOT_REF WAL payload: informational record of a committed snapshot."""

    model_config = ConfigDict(frozen=True, extra="allow")
    v: int = 1
    path: str
    covers_seq: int
    prefix_hash: str
    sha256: str


class _HasPath(Protocol):
    """Anything with a session directory path (a SessionHandle or ReadOnlySession)."""

    path: Path


RefSink = Callable[[NewRecord], Result[Any, Any]]


class SnapshotCadence:
    """Decides when a live session should snapshot: always when forced, else at most every 5 s."""

    def __init__(
        self,
        min_interval_s: float = SNAPSHOT_MIN_INTERVAL_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._min = min_interval_s
        self._clock = clock
        self._last_at: float | None = None
        self._last_seq: int | None = None

    def due(self, covers_seq: int, forced: bool) -> bool:
        """Return True when a snapshot of `covers_seq` should be written now."""
        if covers_seq == self._last_seq:
            return False
        if forced or self._last_at is None:
            return True
        return self._clock() - self._last_at >= self._min

    def written(self, covers_seq: int) -> None:
        """Record that a snapshot of `covers_seq` was committed just now."""
        self._last_at = self._clock()
        self._last_seq = covers_seq


def snapshot_dir(session_dir: Path) -> Path:
    """Return the `snapshots/` directory of a session version."""
    return session_dir / SNAPSHOT_DIR


def prefix_hash_states_at(
    wal_dir: Path, covers: Iterable[int]
) -> Result[tuple[dict[int, Any], int | None], WalError]:
    """Return {n: running hash object after data records <= n} and the last seq seen.

    The scan stops at max(covers): records beyond the largest wanted seq cannot change any
    requested hash, so walking them is pure redundant work.
    """
    wanted = sorted(set(covers))
    out: dict[int, Any] = {}
    h = new_prefix_hash()
    idx = 0
    last: int | None = None
    if not wanted:
        return Ok((out, last))
    for item in WalReader(wal_dir).records():
        if item.is_err:
            _log.error("prefix hash scan of %s hit corruption: %s", wal_dir, item.danger_err)
            return Err(item.danger_err)
        rec: Record = item.danger_ok
        while idx < len(wanted) and wanted[idx] < rec.seq:
            out[wanted[idx]] = h.copy()
            idx += 1
        prefix_hash_update(h, rec)
        last = rec.seq
        if rec.seq >= wanted[-1]:
            break
    while idx < len(wanted):
        out[wanted[idx]] = h.copy()
        idx += 1
    return Ok((out, last))


@propagate
def prefix_hashes_at(
    wal_dir: Path, covers: Iterable[int]
) -> Result[tuple[dict[int, str], int | None], WalError]:
    """Return {n: prefix_hash after all data records with seq <= n} and the last verified seq."""
    scanned = prefix_hash_states_at(wal_dir, covers)
    states, last = scanned.unwrap()
    return Ok(({n: h.hexdigest() for n, h in states.items()}, last))


@propagate
def prefix_hash(wal_dir: Path, covers_seq: int) -> Result[str, SnapshotError]:
    """Return the section 9.2 prefix hash of the verified WAL at `covers_seq`."""
    scanned = prefix_hashes_at(wal_dir, [covers_seq])
    hashes, last = scanned.map_err(lambda e: SnapshotWal(error=e)).unwrap()
    if last is None or covers_seq > last:
        _log.error("snapshot covers_seq %d is beyond verified last_seq %s", covers_seq, last)
        return Err(SnapshotAhead(covers_seq=covers_seq, last_seq=last))
    return Ok(hashes[covers_seq])


def _write_all(fd: int, data: bytes) -> None:
    """Write every byte of `data` to `fd`, looping over short writes."""
    view = memoryview(data)
    while view:
        view = view[os.write(fd, view) :]


@propagate
def _publish_noreplace(tmp: Path, dst: Path) -> Result[Path, SnapshotError]:
    """Give `tmp` its final name without ever replacing an existing file; returns final path."""
    for attempt in range(8):
        target = dst if attempt == 0 else dst.with_name(f"{dst.stem}-{secrets.token_hex(3)}.snap")
        try:
            failpoint("snapshot.rename")
            os.link(tmp, target)
        except FileExistsError:
            _log.warning("snapshot name %s taken; choosing another", target)
            continue
        except OSError as exc:
            if exc.errno not in _LINK_FALLBACK_ERRNOS:
                _log.error("snapshot publish %s failed: %s", target, exc)
                return Err(
                    SnapshotIo(error=durable.DurableIo(errno=exc.errno or errno.EIO, path=target))
                )
            _log.warning("hard links unavailable (%s); using exists-check + rename", exc)
            if target.exists():
                continue
            replaced = durable.atomic_replace(tmp, target)
            replaced.map_err(lambda e: SnapshotIo(error=e)).unwrap()
            return Ok(target)
        try:
            tmp.unlink()
        except OSError as exc:
            _log.warning("could not remove published tmp %s: %s", tmp, exc)
        return Ok(target)
    _log.error("no free snapshot name near %s", dst)
    return Err(SnapshotIo(error=durable.DurableExists(path=dst)))


@propagate
def write_snapshot(  # noqa: PLR0913 - explicit knobs keep tests deterministic
    session: _HasPath,
    state: BaseModel,
    covers_seq: int,
    *,
    prefix_hash_hex: str | None = None,
    lab_module: str = "",
    code_version: dict[str, Any] | None = None,
    ref_sink: RefSink | None = None,
    now: datetime | None = None,
    notes: Sequence[str] | None = None,
) -> Result[Path, SnapshotError]:
    """Write `state` as an atomic snapshot covering WAL seq `covers_seq`; return its path.

    `notes` (all NOTE payloads up to `covers_seq`) is stored additively so replay need not rewalk
    the WAL for them; it is dropped, never failing the snapshot, if it would make it too large.
    """
    session_dir = session.path
    if prefix_hash_hex is None:
        computed = prefix_hash(session_dir / "wal", covers_seq)
        prefix_hash_hex = computed.unwrap()
    body = SnapshotV1(
        covers_seq=covers_seq,
        prefix_hash=prefix_hash_hex,
        code_version=code_version or {},
        lab_module=lab_module,
        state=state.model_dump(mode="json"),
        notes=None if notes is None else list(notes),
    )
    payload = body.model_dump_json().encode("utf-8")
    if len(payload) > MAX_PAYLOAD and notes is not None:
        _log.warning("snapshot with notes is %d bytes; storing it without notes", len(payload))
        body = body.model_copy(update={"notes": None})
        payload = body.model_dump_json().encode("utf-8")
    if len(payload) > MAX_PAYLOAD:
        _log.error("snapshot payload %d bytes exceeds limit", len(payload))
        return Err(SnapshotTooLarge(size=len(payload)))
    frame = encode_frame(SNAPSHOT_FRAME_TYPE, covers_seq, time.time_ns(), FLAG_JSON, payload)
    snaps = snapshot_dir(session_dir)
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%S%fZ")
    final = snaps / f"snap-{covers_seq:012d}-{stamp}.snap"
    tmp = snaps / f".snap-{covers_seq}-{os.getpid()}-{secrets.token_hex(4)}.tmp"
    written = _write_tmp(tmp, frame)
    written.unwrap()
    published = _publish_noreplace(tmp, final)
    if published.is_err:
        return published
    path = published.danger_ok
    try:
        failpoint("snapshot.dirsync")
    except OSError as exc:
        _log.error("snapshot dir flush failpoint: %s", exc)
        return Err(SnapshotIo(error=durable.DurableIo(errno=exc.errno or errno.EIO, path=snaps)))
    flushed = durable.fsync_dir(snaps)
    flushed.map_err(lambda e: SnapshotIo(error=e)).unwrap()
    _log.info("snapshot committed: %s covers_seq=%d", path, covers_seq)
    _emit_ref(ref_sink, path, body, session_dir, frame)
    return Ok(path)


@propagate
def _write_tmp(tmp: Path, frame: bytes) -> Result[None, SnapshotError]:
    """Create `tmp` exclusively, write the frame and fsync it (the file stays if this fails)."""
    created = durable.create_exclusive(tmp)
    fd = created.map_err(lambda e: SnapshotIo(error=e)).unwrap()
    try:
        failpoint("snapshot.write")
        _write_all(fd, frame)
        failpoint("snapshot.fsync")
        synced = durable.fsync_file(fd)
    except OSError as exc:
        _log.error("snapshot tmp write %s failed: %s", tmp, exc)
        return Err(SnapshotIo(error=durable.DurableIo(errno=exc.errno or errno.EIO, path=tmp)))
    finally:
        os.close(fd)
    synced.map_err(lambda e: SnapshotIo(error=e)).unwrap()
    return Ok(None)


def _emit_ref(
    sink: RefSink | None, path: Path, body: SnapshotV1, session_dir: Path, frame: bytes
) -> None:
    """Best-effort SNAPSHOT_REF to the WAL; failure is logged, recovery never depends on it."""
    if sink is None:
        return
    import hashlib  # noqa: PLC0415 - only needed here

    ref = SnapshotRef(
        path=str(path.relative_to(session_dir).as_posix()),
        covers_seq=body.covers_seq,
        prefix_hash=body.prefix_hash,
        sha256=hashlib.sha256(frame).hexdigest(),
    )
    try:
        failpoint("snapshot.ref")
        res = sink(json_record(RecordType.SNAPSHOT_REF, ref))
    except OSError as exc:
        _log.warning("SNAPSHOT_REF for %s not written: %s", path, exc)
        return
    if res.is_err:
        _log.warning("SNAPSHOT_REF for %s refused: %s", path, res.danger_err)


def _parse_snapshot(path: Path) -> SnapshotV1 | None:
    """Read and structurally verify one snapshot file; None (logged) when it must be ignored."""
    try:
        raw = path.read_bytes()
    except OSError as exc:
        _log.warning("ignoring snapshot %s: unreadable: %s", path, exc)
        return None
    decoded = decode_frame(raw)
    if decoded.is_err:
        _log.warning("ignoring snapshot %s: %s", path, decoded.danger_err.reason)
        return None
    rec, end = decoded.danger_ok
    if end != len(raw) or rec.type != SNAPSHOT_FRAME_TYPE or not rec.flags & FLAG_JSON:
        _log.warning("ignoring snapshot %s: wrong frame shape", path)
        return None
    try:
        snap = SnapshotV1.model_validate_json(rec.payload)
    except ValidationError as exc:
        _log.warning("ignoring snapshot %s: invalid payload: %s", path, exc)
        return None
    if snap.v != SNAPSHOT_VERSION or snap.covers_seq != rec.seq:
        _log.warning("ignoring snapshot %s: version or covers_seq mismatch", path)
        return None
    return snap


def list_snapshots(session_dir: Path) -> list[tuple[Path, SnapshotV1]]:
    """Return structurally valid snapshots, newest covers_seq first; invalid ones are ignored."""
    snaps = snapshot_dir(session_dir)
    try:
        names = sorted(p for p in snaps.glob("snap-*.snap") if p.is_file())
    except OSError as exc:
        _log.warning("cannot list %s: %s", snaps, exc)
        return []
    found = [(p, s) for p in names if (s := _parse_snapshot(p)) is not None]
    found.sort(key=lambda item: (item[1].covers_seq, item[0].name), reverse=True)
    return found


@propagate
def load_latest_snapshot_hashed(
    session_dir: Path,
) -> Result[tuple[SnapshotV1, Any] | None, SnapshotError]:
    """Like `load_latest_snapshot` but also return the running prefix hash object at covers_seq."""
    candidates = list_snapshots(session_dir)
    if not candidates:
        _log.info("no usable snapshots in %s", session_dir)
        return Ok(None)
    scanned = prefix_hash_states_at(session_dir / "wal", (s.covers_seq for _, s in candidates))
    states, last = scanned.map_err(lambda e: SnapshotWal(error=e)).unwrap()
    for path, snap in candidates:
        if last is None or snap.covers_seq > last:
            _log.warning(
                "ignoring stale snapshot %s: covers %d > verified %s", path, snap.covers_seq, last
            )
        elif states[snap.covers_seq].hexdigest() != snap.prefix_hash:
            _log.warning("ignoring snapshot %s: prefix hash mismatch at %d", path, snap.covers_seq)
        else:
            _log.info("using snapshot %s covers_seq=%d", path, snap.covers_seq)
            return Ok((snap, states[snap.covers_seq]))
    return Ok(None)


@propagate
def load_latest_snapshot(session_dir: Path) -> Result[SnapshotV1 | None, SnapshotError]:
    """Return the newest snapshot whose prefix hash matches the WAL, or None to replay from 1."""
    got = load_latest_snapshot_hashed(session_dir).unwrap()
    return Ok(None if got is None else got[0])
