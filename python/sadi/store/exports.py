"""Derived exports with provenance sidecars (data-safety.md section 9.3).

An export is written tmp + fsync + no-replace rename, then a `.prov.json` sidecar the same way.
Exports are never overwritten: a name collision takes the next number. They are derived and
losable (invariant I7): every export can be regenerated from the WAL chain.
"""

# frob:ticket 01M6W7R04QJTECCTSV9EY2JADK
from __future__ import annotations

import hashlib
import os
import re
import secrets
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ConfigDict
from typani import Err, ErrorSet, Ok, Result, propagate

from sadi.logging_setup import get_logger
from sadi.store import durable, snapshot
from sadi.store.durable import DurableError
from sadi.store.failpoints import failpoint
from sadi.store.names import sanitize_name
from sadi.store.records import NewRecord, RecordType, json_record

_log = get_logger(__name__)
_T = TypeVar("_T")

EXPORT_DIR = "exports"
EXPORT_VERSION = 1
PROV_SUFFIX = ".prov.json"
_MAX_ATTEMPTS = 16
_NUM_RE = re.compile(r"^(\d{4,})-")
_EXT_RE = re.compile(r"^[A-Za-z0-9]{1,16}$")


class ExportError(ErrorSet):
    """Export failure; details are logged, the description says what to do."""

    BadName = "Export kind, basename or extension is not usable as a file name"
    Io = "A disk error occurred while writing the export; the recording itself is safe"
    Wal = "The recording could not be verified, so no provenance can be recorded; see the log"
    Ahead = "covers_seq is beyond the verified log; export only data that is already recorded"
    NoFreeName = "No free export number could be reserved; see the log"


class _HasPath(Protocol):
    """Anything with a session directory path (a SessionHandle or ReadOnlySession)."""

    path: Path


RefSink = Callable[[NewRecord], Result[Any, Any]]


class ExportProvenanceV1(BaseModel):
    """Sidecar describing exactly which WAL prefix and code produced an export."""

    model_config = ConfigDict(frozen=True, extra="allow")
    v: int = EXPORT_VERSION
    kind: str
    path: str
    sha256: str
    size: int
    created: datetime
    covers_seq: int
    prefix_hash: str
    snapshot_path: str | None = None
    code_version: dict[str, Any] = {}
    lab_module: str = ""
    parameters: dict[str, Any] = {}


class ExportRef(BaseModel):
    """EXPORT_REF WAL payload: informational record of a committed export."""

    model_config = ConfigDict(frozen=True, extra="allow")
    v: int = 1
    path: str
    sha256: str
    covers_seq: int
    prefix_hash: str


class ExportResult(BaseModel):
    """Paths of a committed export; `sidecar` is None when only the data file was published."""

    model_config = ConfigDict(frozen=True)
    path: Path
    sidecar: Path | None
    provenance: ExportProvenanceV1 | None


class ExportListing(BaseModel):
    """One file under exports/<kind>/; `complete` means its sidecar exists."""

    model_config = ConfigDict(frozen=True)
    path: Path
    complete: bool


def export_dir(session_dir: Path, kind: str) -> Path:
    """Return the `exports/<kind>/` directory of a session version."""
    return session_dir / EXPORT_DIR / kind


def _data_names(directory: Path) -> list[str]:
    """Names of published export data files (no dotfiles, no sidecars) in `directory`."""
    try:
        return sorted(
            p.name
            for p in directory.iterdir()
            if not p.name.startswith(".") and not p.name.endswith(PROV_SUFFIX)
        )
    except FileNotFoundError:
        return []


def next_number(directory: Path) -> int:
    """Return one more than the highest NNNN prefix among published exports (1 when none)."""
    nums = [int(m.group(1)) for n in _data_names(directory) if (m := _NUM_RE.match(n))]
    return max(nums, default=0) + 1


def list_exports(session_dir: Path, kind: str) -> list[ExportListing]:
    """List exports of a kind; one without a sidecar is `incomplete` and must not be trusted."""
    directory = export_dir(session_dir, kind)
    out = [
        ExportListing(path=directory / n, complete=(directory / (n + PROV_SUFFIX)).is_file())
        for n in _data_names(directory)
    ]
    for item in out:
        if not item.complete:
            _log.warning("export %s has no provenance sidecar: incomplete", item.path)
    return out


def _io_err(exc: OSError, path: Path) -> Result[_T, ExportError]:
    """Log an OS failure and map it to ExportError.Io."""
    _log.error("export io failure at %s: %s", path, exc)
    return Err(ExportError.Io)


def _write_all(fd: int, data: bytes) -> None:
    """Write every byte of `data` to `fd`, looping over short writes."""
    view = memoryview(data)
    while view:
        view = view[os.write(fd, view) :]


def _write_tmp(tmp: Path, data: bytes, fp: str) -> Result[None, ExportError]:
    """Create `tmp` exclusively, write `data` and fsync it (the tmp stays if this fails)."""
    created = durable.create_exclusive(tmp)
    if created.is_err:
        _log.error("cannot create export tmp %s: %s", tmp, created.danger_err)
        return Err(ExportError.Io)
    fd = created.danger_ok
    try:
        failpoint(f"{fp}.write")
        _write_all(fd, data)
        failpoint(f"{fp}.fsync")
        synced = durable.fsync_file(fd)
    except OSError as exc:
        return _io_err(exc, tmp)
    finally:
        os.close(fd)
    if synced.is_err:
        _log.error("fsync of export tmp %s failed: %s", tmp, synced.danger_err)
        return Err(ExportError.Io)
    return Ok(None)


def _provenance_bounds(
    session_dir: Path, covers_seq: int | None
) -> Result[tuple[int, str], ExportError]:
    """Return (covers_seq, prefix_hash) for the verified WAL, or for an explicit covers_seq."""
    wal_dir = session_dir / "wal"
    if covers_seq is None:
        scanned = snapshot.prefix_hashes_at(wal_dir, [sys.maxsize])
        if scanned.is_err:
            _log.error("export provenance scan failed: %s", scanned.danger_err)
            return Err(ExportError.Wal)
        hashes, last = scanned.danger_ok
        return Ok((last or 0, hashes[sys.maxsize]))
    computed = snapshot.prefix_hash(wal_dir, covers_seq)
    if computed.is_err:
        err = computed.danger_err
        _log.error("export covers_seq %d rejected: %s", covers_seq, err)
        return Err(
            ExportError.Ahead if isinstance(err, snapshot.SnapshotAhead) else ExportError.Wal
        )
    return Ok((covers_seq, computed.danger_ok))


def _publish(
    directory: Path, tmp: Path, stem_fmt: Callable[[int], str]
) -> Result[Path, ExportError]:
    """Rename `tmp` to the first free numbered name; an existing file is never replaced."""
    number = next_number(directory)
    for _ in range(_MAX_ATTEMPTS):
        target = directory / stem_fmt(number)
        try:
            failpoint("export.rename")
        except OSError as exc:
            return _io_err(exc, target)
        renamed = durable.rename_noreplace(tmp, target)
        if renamed.is_ok:
            return Ok(target)
        err: DurableError = renamed.danger_err
        if isinstance(err, durable.DurableExists):
            _log.warning("export name %s taken; trying next number", target)
            number += 1
            continue
        _log.error("export publish %s failed: %s", target, err)
        return Err(ExportError.Io)
    _log.error("no free export number in %s after %d tries", directory, _MAX_ATTEMPTS)
    return Err(ExportError.NoFreeName)


def _tmp_path(directory: Path, label: str) -> Path:
    """Return a fresh dot-prefixed tmp path next to the final location."""
    return directory / f".{label}.tmp-{os.getpid()}-{secrets.token_hex(4)}"


@propagate
def _write_sidecar(final: Path, prov: ExportProvenanceV1) -> Result[Path, ExportError]:
    """Write the provenance sidecar next to `final` (tmp, fsync, no-replace rename)."""
    sidecar = final.with_name(final.name + PROV_SUFFIX)
    data = (prov.model_dump_json(indent=2) + "\n").encode("utf-8")
    tmp = _tmp_path(final.parent, "prov")
    written = _write_tmp(tmp, data, "export.sidecar")
    written.unwrap()
    renamed = durable.rename_noreplace(tmp, sidecar)
    if renamed.is_err:
        _log.error("sidecar publish %s failed: %s", sidecar, renamed.danger_err)
        return Err(ExportError.Io)
    return Ok(sidecar)


def _emit_ref(sink: RefSink | None, rel: str, prov: ExportProvenanceV1) -> None:
    """Best-effort EXPORT_REF to the WAL; failure is logged, nothing depends on it."""
    if sink is None:
        return
    ref = ExportRef(
        path=rel, sha256=prov.sha256, covers_seq=prov.covers_seq, prefix_hash=prov.prefix_hash
    )
    try:
        failpoint("export.ref")
        res = sink(json_record(RecordType.EXPORT_REF, ref))
    except OSError as exc:
        _log.warning("EXPORT_REF for %s not written: %s", rel, exc)
        return
    if res.is_err:
        _log.warning("EXPORT_REF for %s refused: %s", rel, res.danger_err)


@propagate
def write_export(  # noqa: PLR0913 - explicit knobs keep tests deterministic
    session: _HasPath,
    kind: str,
    basename: str,
    ext: str,
    payload: bytes,
    *,
    covers_seq: int | None = None,
    snapshot_path: Path | None = None,
    code_version: dict[str, Any] | None = None,
    lab_module: str = "",
    parameters: dict[str, Any] | None = None,
    ref_sink: RefSink | None = None,
    now: datetime | None = None,
) -> Result[ExportResult, ExportError]:
    """Atomically publish `payload` as a new numbered export with a provenance sidecar."""
    session_dir = session.path
    if not _EXT_RE.match(ext):
        _log.error("unusable export extension %r", ext)
        return Err(ExportError.BadName)
    kind = sanitize_name(kind)
    base = sanitize_name(basename)
    bounds = _provenance_bounds(session_dir, covers_seq)
    seq, phash = bounds.unwrap()
    when = now or datetime.now(UTC)
    stamp = when.strftime("%Y%m%dT%H%M%SZ")
    directory = export_dir(session_dir, kind)
    try:
        failpoint("export.mkdir")
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return _io_err(exc, directory)
    tmp = _tmp_path(directory, base)
    written = _write_tmp(tmp, payload, "export.data")
    written.unwrap()
    published = _publish(directory, tmp, lambda n: f"{n:04d}-{stamp}-{base}.{ext}")
    final = published.unwrap()
    rel = final.relative_to(session_dir).as_posix()
    prov = ExportProvenanceV1(
        kind=kind,
        path=rel,
        sha256=hashlib.sha256(payload).hexdigest(),
        size=len(payload),
        created=when,
        covers_seq=seq,
        prefix_hash=phash,
        snapshot_path=snapshot_path.relative_to(session_dir).as_posix() if snapshot_path else None,
        code_version=code_version or {},
        lab_module=lab_module,
        parameters=parameters or {},
    )
    sidecar = _write_sidecar(final, prov)
    if sidecar.is_err:
        _log.error("export %s published without sidecar: it is incomplete", final)
        return Err(sidecar.danger_err)
    _log.info("export committed: %s covers_seq=%d", final, seq)
    _emit_ref(ref_sink, rel, prov)
    return Ok(ExportResult(path=final, sidecar=sidecar.danger_ok, provenance=prov))
