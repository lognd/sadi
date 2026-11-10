"""Emergency spill import (data-safety 6.5 step 4): spill files become new session versions.

A spill file is a plain segment file (same framing as the WAL). At start we discover them,
verify header and every frame CRC, and copy the verified prefix into a NEW version directory.
The spill file is never modified, truncated or deleted; unverifiable trailing bytes are
reported (offset, length, SHA-256) and stay in the original file.
"""

# frob:ticket 01M6WEFG8X91K7313MGJQPFW6F
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
import uuid
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict
from typani import Err, Ok, Result, propagate

from sadi.logging_setup import get_logger
from sadi.store.durable import (
    DurableError,
    DurableIo,
    create_exclusive,
    fsync_dir,
    fsync_file,
    rename_noreplace,
)
from sadi.store.manifest import Manifest, read_manifest
from sadi.store.records import Record, decode_frame, encode_frame
from sadi.store.session import (
    SESSIONS_DIRNAME,
    SessionError,
    _init_dir,
    _slug,
    _take_version,
    session_is_synthetic,
)
from sadi.store.wal import (
    SEGMENT_HEADER_LEN,
    SegmentHeader,
    WalError,
    WalReader,
    decode_segment_header,
    encode_segment_header,
    segment_name,
)

_log = get_logger(__name__)

SPILL_DIRNAME = "spill"
SPILL_GLOB = "*.wal"
TEMP_SPILL_GLOB = "sadi-spill-*.wal"
MARKER_SUFFIX = ".imported.json"
IMPORT_SLUG = "spill-import"
FAILED_SUFFIX = ".join-failed.json"
#: Free space kept in reserve beyond the copy itself before a join is attempted (M4).
JOIN_MARGIN_BYTES = 64 * 1024 * 1024


class SpillError(BaseModel):
    """Base of all spill-import failures; `hint` is shown in the UI."""

    model_config = ConfigDict(frozen=True)
    hint: str = ""


class SpillIo(SpillError):
    """Reading the spill file or writing the new version failed at the OS level."""

    error: DurableError
    path: Path | None = None


class SpillHeaderInvalid(SpillError):
    """The spill file has no valid segment header; nothing can be imported from it."""

    path: Path
    error: WalError
    hint: str = "The spill file is left untouched for manual forensics."


class SpillEmpty(SpillError):
    """The spill file has a valid header but no verified record; nothing to import."""

    path: Path
    hint: str = "The spill file is left untouched for manual forensics."


class SpillSession(SpillError):
    """Creating the new version directory failed."""

    error: SessionError


class SpillVerifyFailed(SpillError):
    """The imported segment did not re-verify; the new version dir is kept for inspection."""

    version_dir: Path
    error: WalError


class SpillTail(BaseModel):
    """Unverified bytes at the end of a spill file; left in place, never truncated."""

    model_config = ConfigDict(frozen=True)
    offset: int
    length: int
    sha256: str
    reason: str


class SpillScan(BaseModel):
    """Read-only verification result of one spill file."""

    model_config = ConfigDict(frozen=True)
    path: Path
    size: int
    sha256: str
    header: SegmentHeader
    valid_bytes: int
    record_count: int
    first_seq: int | None
    last_seq: int | None
    tail: SpillTail | None


class SpillWriteFailed(SpillError):
    """Every spill location refused the records; they stay in memory and nothing was lost."""

    attempts: tuple[str, ...]
    hint: str = "Free disk space or reattach the drive, then retry Close session."


class ImportReport(BaseModel):
    """What one import did: where the data went and what (if anything) was left behind."""

    model_config = ConfigDict(frozen=True)
    source: Path
    version_dir: Path
    record_count: int
    first_seq: int
    last_seq: int
    parent: str | None
    continuity_ok: bool | None
    tail: SpillTail | None
    marker_written: bool


def user_data_dir() -> Path:
    """Return the per-user SADI data directory for this OS (data-safety 8.1)."""
    home = Path.home()
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        return (
            Path(base) if base is not None and base != "" else home / "AppData" / "Local"
        ) / "sadi"
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "sadi"
    xdg = os.environ.get("XDG_DATA_HOME")
    return (Path(xdg) if xdg is not None and xdg != "" else home / ".local" / "share") / "sadi"


def discover_spills(
    data_root: Path, user_dir: Path | None = None, temp_dir: Path | None = None
) -> list[Path]:
    """List spill files from data-root, user data dir and OS temp, in that order, de-duplicated."""
    places = (
        (data_root / SPILL_DIRNAME, SPILL_GLOB),
        ((user_dir or user_data_dir()) / SPILL_DIRNAME, SPILL_GLOB),
        (temp_dir or Path(tempfile.gettempdir()), TEMP_SPILL_GLOB),
    )
    found: list[Path] = []
    seen: set[Path] = set()
    for directory, pattern in places:
        try:
            candidates = sorted(directory.glob(pattern)) if directory.is_dir() else []
        except OSError as exc:
            _log.warning("cannot list spill dir %s: %s", directory, exc)
            continue
        for path in candidates:
            real = path.resolve()
            if path.is_file() and real not in seen:
                seen.add(real)
                found.append(path)
    _log.info("discovered %d spill file(s)", len(found))
    return found


def scan_spill(path: Path) -> Result[SpillScan, SpillError]:
    """Verify a spill file read-only: header, per-frame CRC-32C and dense seqs; never writes."""
    try:
        data = path.read_bytes()
    except OSError as exc:
        _log.error("cannot read spill %s: %s", path, exc)
        return Err(SpillIo(error=DurableIo(errno=exc.errno or 5, path=path), path=path))
    header = decode_segment_header(data[:SEGMENT_HEADER_LEN], 1)
    if header.is_err:
        _log.error("spill %s: invalid segment header: %s", path, header.danger_err)
        return Err(SpillHeaderInvalid(path=path, error=header.danger_err))
    hdr = header.danger_ok
    pos = SEGMENT_HEADER_LEN
    expected = hdr.first_seq
    count = 0
    reason = ""
    while pos < len(data):
        frame = decode_frame(data, pos)
        if frame.is_err:
            reason = frame.danger_err.reason
            break
        rec, end = frame.danger_ok
        if rec.seq != expected:
            reason = f"seq {rec.seq} where {expected} expected"
            break
        expected += 1
        count += 1
        pos = end
    tail: SpillTail | None = None
    if pos < len(data):
        tail = SpillTail(
            offset=pos,
            length=len(data) - pos,
            sha256=hashlib.sha256(data[pos:]).hexdigest(),
            reason=reason,
        )
        _log.warning(
            "spill %s: %d unverifiable tail bytes at %d (%s)", path, tail.length, pos, reason
        )
    scan = SpillScan(
        path=path,
        size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        header=hdr,
        valid_bytes=pos,
        record_count=count,
        first_seq=hdr.first_seq if count else None,
        last_seq=expected - 1 if count else None,
        tail=tail,
    )
    _log.info("spill %s: %d verified records, tail=%s", path, count, tail is not None)
    return Ok(scan)


def _marker_path(spill: Path) -> Path:
    """Return the sidecar marker path recording that `spill` was imported."""
    return spill.with_name(spill.name + MARKER_SUFFIX)


def _already_imported(scan: SpillScan) -> bool:
    """Return True when a marker next to the spill names this exact file content."""
    marker = _marker_path(scan.path)
    try:
        return bool(json.loads(marker.read_text("utf-8")).get("sha256") == scan.sha256)
    except (OSError, ValueError, AttributeError):
        return False


def _write_marker(scan: SpillScan, version_dir: Path) -> bool:
    """Create the sidecar marker exclusively (the spill file itself is untouched)."""
    body = {
        "sha256": scan.sha256,
        "size": scan.size,
        "version_dir": str(version_dir),
        "imported": datetime.now(UTC).isoformat(),
        "valid_bytes": scan.valid_bytes,
    }
    created = create_exclusive(_marker_path(scan.path))
    if created.is_err:
        _log.warning("cannot write import marker for %s: %s", scan.path, created.danger_err)
        return False
    fd = created.danger_ok
    try:
        os.write(fd, json.dumps(body, indent=2).encode("ascii") + b"\n")
        fsync_file(fd)
    except OSError as exc:
        _log.warning("marker write for %s failed: %s", scan.path, exc)
        return False
    finally:
        os.close(fd)
    return True


def _find_parent(data_root: Path, session_uuid: uuid.UUID) -> Manifest | None:
    """Find the newest version whose manifest uuid matches the spill header, if any."""
    best: Manifest | None = None
    sessions = data_root / SESSIONS_DIRNAME
    try:
        dirs = sorted(p for p in sessions.iterdir() if p.is_dir())
    except OSError:
        return None
    for d in dirs:
        mf = read_manifest(d)
        if mf.is_err or mf.danger_ok is None:
            continue
        m = mf.danger_ok
        if m.session_uuid == str(session_uuid) and (best is None or m.version > best.version):
            best = m
    return best


@propagate
def _write_segment(
    wal_dir: Path, header: bytes, frames: Iterable[bytes]
) -> Result[None, DurableError]:
    """Create seg-000001.wal exclusively, write header and verified frames, fsync file and dir."""
    created = create_exclusive(wal_dir / segment_name(1))
    fd = created.unwrap()
    try:
        for chunk in (header, *frames):
            view = memoryview(chunk)
            while view:
                view = view[os.write(fd, view) :]
        synced = fsync_file(fd)
    except OSError as exc:
        return Err(DurableIo(errno=exc.errno or 5, path=wal_dir))
    finally:
        os.close(fd)
    if synced.is_err:
        return synced
    return fsync_dir(wal_dir)


class _Join(BaseModel):
    """A verified plan to join a spill onto its parent: the parent WAL plus the new tail."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)
    wal_dir: Path
    parent_records: int
    tail: tuple[Record, ...]


def _spill_records(data: bytes, scan: SpillScan) -> list[Record]:
    """Decode the verified frames of a spill (already CRC-checked by `scan_spill`)."""
    out: list[Record] = []
    pos = SEGMENT_HEADER_LEN
    while pos < scan.valid_bytes:
        rec, end = decode_frame(data, pos).danger_ok
        out.append(rec)
        pos = end
    return out


def _same_frame(a: Record, b: Record) -> bool:
    """True when two records agree on every logical field (seq is compared by the caller)."""
    return (a.type, a.wall_ns, a.flags, a.payload) == (b.type, b.wall_ns, b.flags, b.payload)


def _failed_marker_path(spill: Path) -> Path:
    """Return the sidecar path recording that a join of `spill` already failed once."""
    return spill.with_name(spill.name + FAILED_SUFFIX)


def _join_failed_before(scan: SpillScan) -> bool:
    """Return True when a failed-join marker names this exact spill content (M4)."""
    try:
        marker = json.loads(_failed_marker_path(scan.path).read_text("utf-8"))
        return bool(marker.get("sha256") == scan.sha256)
    except (OSError, ValueError, AttributeError):
        return False


def _write_failed_marker(scan: SpillScan, partial: Path | None, why: str) -> None:
    """Best-effort exclusive marker naming the partial join dir so restarts never retry the join."""
    body = {
        "sha256": scan.sha256,
        "partial_dir": str(partial) if partial is not None else None,
        "reason": why,
        "recorded": datetime.now(UTC).isoformat(),
    }
    created = create_exclusive(_failed_marker_path(scan.path))
    if created.is_err:
        _log.warning("cannot write failed-join marker for %s: %s", scan.path, created.danger_err)
        return
    fd = created.danger_ok
    try:
        os.write(fd, json.dumps(body, indent=2).encode("ascii") + b"\n")
        fsync_file(fd)
    except OSError as exc:
        _log.warning("failed-join marker write for %s failed: %s", scan.path, exc)
    finally:
        os.close(fd)


def _wal_bytes(wal_dir: Path) -> int:
    """Total size of the WAL segment files in `wal_dir` (0 when unreadable)."""
    try:
        return sum(p.stat().st_size for p in wal_dir.glob("seg-*.wal"))
    except OSError:
        return 0


# frob:ticket 01M729648PC6N7FK6D2J6H1ETV
def _plan_join(
    sessions: Path, parent: Manifest, scan: SpillScan, spill_recs: list[Record]
) -> _Join | None:
    """Return a join plan, or None (with a logged reason) when the spill must stay a fragment.

    The spill may overlap the parent (a failed fsync leaves the batch written but not durable):
    `parent.first_seq <= spill.first_seq <= parent.last_seq + 1`, every gap seq being a SEAL, and
    the overlapping frames must be identical. Nothing is joined without enough free space.
    """
    wal_dir = sessions / parent.dir_name / "wal"
    if _join_failed_before(scan):
        _log.warning("join of %s failed earlier (marker present); kept as fragment", scan.path)
        return None
    report = WalReader.scan(wal_dir)
    if report.is_err:
        _log.warning("parent WAL %s does not verify (%s); fragment", wal_dir, report.danger_err)
        return None
    rep = report.danger_ok
    first = scan.first_seq
    if rep.last_seq is None or rep.first_seq is None or first is None:
        return None
    gap = set(range(rep.last_seq + 1, first))
    if first < rep.first_seq or not gap <= set(rep.seal_seqs):
        _log.warning(
            "spill %s does not continue parent %s (parent seq %s..%s, spill first_seq=%s); "
            "kept as fragment",
            scan.path,
            wal_dir,
            rep.first_seq,
            rep.last_seq,
            first,
        )
        return None
    by_seq = {r.seq: r for r in spill_recs}
    for item in WalReader(wal_dir).records(from_seq=first):
        rec = item.danger_ok  # the parent was verified by the scan above
        theirs = by_seq.get(rec.seq)
        if theirs is not None and not _same_frame(rec, theirs):
            _log.warning(
                "spill %s seq %d differs from parent %s; kept as fragment",
                scan.path,
                rec.seq,
                wal_dir,
            )
            return None
    need = _wal_bytes(wal_dir) + scan.size + JOIN_MARGIN_BYTES
    try:
        free = shutil.disk_usage(sessions).free
    except OSError as exc:
        _log.warning("cannot read free space for %s (%s); fragment", sessions, exc)
        return None
    if free < need:
        _log.warning(
            "join deferred for %s: not enough space (%d free, %d needed); kept as fragment",
            scan.path,
            free,
            need,
        )
        return None
    tail = tuple(r for r in spill_recs if r.seq > rep.last_seq)
    return _Join(wal_dir=wal_dir, parent_records=rep.record_count, tail=tail)


# frob:ticket 01M729648PC6N7FK6D2J6H1ETV
def _combined_frames(join: _Join) -> Iterator[bytes]:
    """Yield parent data frames then the new spill tail, renumbered densely (seals dropped)."""
    seq = 0
    for item in WalReader(join.wal_dir).records():
        rec = item.danger_ok  # the prefix was verified by `_plan_join`
        seq += 1
        yield encode_frame(rec.type, seq, rec.wall_ns, rec.flags, rec.payload)
    for rec in join.tail:
        seq += 1
        yield encode_frame(rec.type, seq, rec.wall_ns, rec.flags, rec.payload)


def import_spill(data_root: Path, scan: SpillScan) -> Result[ImportReport, SpillError]:
    """Import `scan` as a new version dir; the spill file and the parent are never modified.

    When the spill continues (or overlaps) a verified parent and there is room, the successor is
    self-contained: the parent's records plus the spill tail. Otherwise, or if writing the join
    fails, the spill alone is kept as a fragment (never dropped, never superseding its parent).
    """
    if scan.record_count == 0 or scan.first_seq is None or scan.last_seq is None:
        return Err(SpillEmpty(path=scan.path))
    parent = _find_parent(data_root, scan.header.session_uuid)
    sessions = data_root / SESSIONS_DIRNAME
    try:
        sessions.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return Err(SpillIo(error=DurableIo(errno=exc.errno or 5, path=sessions), path=sessions))
    data = scan.path.read_bytes()
    join = (
        None if parent is None else _plan_join(sessions, parent, scan, _spill_records(data, scan))
    )
    result = _import_version(data_root, scan, data, parent, join)
    if join is not None and result.is_err and isinstance(result.danger_err, SpillIo):
        err = result.danger_err
        _log.error("join of %s failed (%s); importing the fragment instead", scan.path, err)
        _write_failed_marker(scan, err.path, str(err.error))
        return _import_version(data_root, scan, data, parent, None, continuity_hint=False)
    return result


@propagate
def _import_version(
    data_root: Path,
    scan: SpillScan,
    data: bytes,
    parent: Manifest | None,
    join: _Join | None,
    continuity_hint: bool | None = None,
) -> Result[ImportReport, SpillError]:
    """Write one new version dir for `scan` (joined when `join` is set, else a fragment)."""
    assert scan.first_seq is not None and scan.last_seq is not None
    sessions = data_root / SESSIONS_DIRNAME
    now = datetime.now(UTC)
    if parent is not None:
        family, start = parent.family, parent.version + 1
    else:
        family, start = f"{now.strftime('%Y%m%dT%H%M%SZ')}-{_slug(IMPORT_SLUG)}", 1
    taken = _take_version(sessions, family, start)
    path, ver = taken.map_err(lambda e: SpillSession(error=e)).unwrap()
    new_uuid = uuid.uuid4()
    total = scan.last_seq if join is None else join.parent_records + len(join.tail)
    # Provenance (M3): inherit from the parent; an orphan has none, so it is NOT labelled real.
    if parent is not None:
        synthetic = session_is_synthetic(sessions / parent.dir_name)
    else:
        synthetic = True
        _log.warning("orphan spill %s has no parent; imported as synthetic/unknown", scan.path)
    manifest = Manifest(
        session_uuid=str(new_uuid),
        dir_name=path.name,
        family=family,
        version=ver,
        parent=parent.dir_name if parent is not None else None,
        parent_last_seq=parent.last_seq if parent is not None else None,
        created=now,
        lab_module=parent.lab_module if parent is not None else "",
        specimen=parent.specimen if parent is not None else {},
        last_seq=total,
        synthetic=synthetic,
        spill_import="joined" if join is not None else "fragment",
    )
    handle = _init_dir(path, manifest).map_err(lambda e: SpillSession(error=e)).unwrap()
    if join is not None:
        header = encode_segment_header(1, 1, new_uuid)
        frames: Iterable[bytes] = _combined_frames(join)
    else:
        header = encode_segment_header(1, scan.first_seq, new_uuid)
        frames = (data[SEGMENT_HEADER_LEN : scan.valid_bytes],)
    written = _write_segment(path / "wal", header, frames)
    if written.is_err:
        handle.close("crashed")
        return Err(SpillIo(error=written.danger_err, path=path))
    verified = WalReader.scan(path / "wal")
    closed = handle.close("closed")
    if closed.is_err:
        _log.warning("closing imported session %s: %s", path, closed.danger_err)
    if verified.is_err:
        _log.error("imported segment in %s failed re-verification", path)
        return Err(SpillVerifyFailed(version_dir=path, error=verified.danger_err))
    marked = _write_marker(scan, path)
    if continuity_hint is not None:
        continuity = continuity_hint
    else:
        continuity = None if parent is None or parent.last_seq is None else join is not None
    if continuity is False:
        _log.warning("spill %s seq does not continue parent %s", scan.path, parent)
    _log.info("imported %s as %s (%d records)", scan.path, path, scan.record_count)
    return Ok(
        ImportReport(
            source=scan.path,
            version_dir=path,
            record_count=scan.record_count,
            first_seq=scan.first_seq,
            last_seq=scan.last_seq,
            parent=manifest.parent,
            continuity_ok=continuity,
            tail=scan.tail,
            marker_written=marked,
        )
    )


def import_all_spills(
    data_root: Path, user_dir: Path | None = None, temp_dir: Path | None = None
) -> list[tuple[Path, Result[ImportReport | None, SpillError]]]:
    """Discover, verify and import every spill at start; Ok(None) means already imported."""
    outcomes: list[tuple[Path, Result[ImportReport | None, SpillError]]] = []
    seen_content: dict[str, Path] = {}  # frob:ticket 01M729648PC6N7FK6D2J6H1ETV
    for spill in discover_spills(data_root, user_dir, temp_dir):
        scanned = scan_spill(spill)
        if scanned.is_err:
            outcomes.append((spill, Err(scanned.danger_err)))
            continue
        scan = scanned.danger_ok
        if _already_imported(scan):
            _log.info("spill %s already imported, skipping", spill)
            outcomes.append((spill, Ok(None)))
            continue
        twin = seen_content.get(scan.sha256)
        if twin is not None:
            _log.info(
                "spill %s is byte-identical to imported %s; marking, no new version", spill, twin
            )
            _write_marker(scan, twin)
            outcomes.append((spill, Ok(None)))
            continue
        imported = import_spill(data_root, scan)
        if imported.is_err:
            outcomes.append((spill, Err(imported.danger_err)))
        else:
            seen_content[scan.sha256] = imported.danger_ok.version_dir
            outcomes.append((spill, Ok(imported.danger_ok)))
    return outcomes


def _dense_runs(records: list[Record]) -> list[list[Record]]:
    """Split records into runs of consecutive seqs (a spill segment must be dense)."""
    runs: list[list[Record]] = []
    for rec in records:
        if runs and rec.seq == runs[-1][-1].seq + 1:
            runs[-1].append(rec)
        else:
            runs.append([rec])
    return runs


# frob:ticket 01M726PZKE3CYNC5NABZC56HT2
def _publish_spill(directory: Path, name: str, blob: bytes) -> Result[Path, DurableError]:
    """Write `blob` to a tmp file, fsync, publish under `name` without replace, fsync the dir."""
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return Err(DurableIo(errno=exc.errno or 5, path=directory))
    tmp = directory / f".{name}.{uuid.uuid4().hex[:8]}.tmp"
    created = create_exclusive(tmp)
    if created.is_err:
        return Err(created.danger_err)
    fd = created.danger_ok
    try:
        view = memoryview(blob)
        while view:
            view = view[os.write(fd, view) :]
        synced = fsync_file(fd)
    except OSError as exc:
        return Err(DurableIo(errno=exc.errno or 5, path=tmp))
    finally:
        os.close(fd)
    if synced.is_err:
        return Err(synced.danger_err)
    final = directory / name
    moved = rename_noreplace(tmp, final)
    if moved.is_err:
        return Err(moved.danger_err)
    return Ok(final)


# frob:ticket 01M729648PC6N7FK6D2J6H1ETV
def spill_name(session_uuid: uuid.UUID, first_seq: int) -> str:
    """Deterministic spill name for (session uuid, first seq): Close retries do not pile up."""
    return f"sadi-spill-{session_uuid.hex}-{first_seq:010d}.wal"


# frob:ticket 01M729648PC6N7FK6D2J6H1ETV
def _publish_idempotent(directory: Path, name: str, blob: bytes) -> Result[Path, DurableError]:
    """Publish `blob` as `name`; an identical existing file is reused, a different one is kept.

    When `name` already holds different bytes (a retry that holds more or other records) the
    new blob goes under a content-hash suffixed name instead: nothing is ever overwritten.
    """
    final = directory / name
    try:
        body = blob[SEGMENT_HEADER_LEN:]  # the header carries a timestamp; compare the frames
        if final.is_file():
            if final.read_bytes()[SEGMENT_HEADER_LEN:] == body:
                _log.info("spill %s already present with identical content; reusing", final)
                return Ok(final)
            digest = hashlib.sha256(body).hexdigest()[:12]
            name = f"{final.stem}-{digest}{final.suffix}"
            _log.warning("spill %s exists with different content; writing %s", final, name)
            alt = directory / name
            if alt.is_file() and alt.read_bytes()[SEGMENT_HEADER_LEN:] == body:
                return Ok(alt)
    except OSError as exc:
        return Err(DurableIo(errno=exc.errno or 5, path=final))
    return _publish_spill(directory, name, blob)


# frob:ticket 01M726PZKE3CYNC5NABZC56HT2
def write_spill(
    records: list[Record],
    session_uuid: uuid.UUID,
    data_root: Path,
    user_dir: Path | None = None,
    temp_dir: Path | None = None,
) -> Result[list[Path], SpillWriteFailed]:
    """Spill undurable `records` atomically (never overwriting) to data-root, user dir, then temp.

    One file per dense seq run; the first location that accepts a run wins. Any run that no
    location accepts makes the whole call Err so the caller keeps the records in memory.
    """
    places = (
        data_root / SPILL_DIRNAME,
        (user_dir or user_data_dir()) / SPILL_DIRNAME,
        temp_dir or Path(tempfile.gettempdir()),
    )
    paths: list[Path] = []
    attempts: list[str] = []
    for run in _dense_runs(records):
        header = encode_segment_header(1, run[0].seq, session_uuid)
        frames = b"".join(encode_frame(r.type, r.seq, r.wall_ns, r.flags, r.payload) for r in run)
        blob = header + frames
        name = spill_name(session_uuid, run[0].seq)
        for directory in places:
            published = _publish_idempotent(directory, name, blob)
            if published.is_ok:
                _log.warning(
                    "spilled %d undurable record(s) seq %d..%d to %s",
                    len(run),
                    run[0].seq,
                    run[-1].seq,
                    published.danger_ok,
                )
                paths.append(published.danger_ok)
                break
            attempts.append(f"{directory}: {published.danger_err}")
            _log.error("spill to %s failed: %s", directory, published.danger_err)
        else:
            return Err(SpillWriteFailed(attempts=tuple(attempts)))
    return Ok(paths)
