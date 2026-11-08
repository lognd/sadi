"""Read-only survey of recorded sessions: the facts the SESS and WAL checks judge."""

# frob:ticket 01M6WJHRTR9DZMZGR04GT1SN0C
from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from sadi.logging_setup import get_logger
from sadi.store.exports import PROV_SUFFIX
from sadi.store.manifest import read_manifest
from sadi.store.records import RecordType
from sadi.store.session import SESSIONS_DIRNAME, proc_start_token, read_lock_holder
from sadi.store.snapshot import list_snapshots, prefix_hashes_at, snapshot_dir
from sadi.store.wal import (
    WalCorrupt,
    WalReader,
    WalSegmentHeaderInvalid,
    WalUnsupportedFormat,
)

_log = get_logger(__name__)

SKIP_BYTES = 256 * 1024 * 1024
DEEP_TIMEOUT_S = 120.0
_NAME_RE = re.compile(r"^\d{8}T\d{6}Z-[a-z0-9-]+\.v\d{3}$")
_VER_RE = re.compile(r"^(?P<family>.+)\.v(?P<ver>\d{3})$")
_SEG_RE = re.compile(r"^seg-\d{6}\.wal$")

ManifestStatus = Literal["ok", "missing", "unparseable"]
WalStatus = Literal[
    "ok",
    "none",
    "skipped",
    "timeout",
    "torn-tail",
    "corrupt",
    "seal-mismatch",
    "seq-gap",
    "unsupported-format",
    "header-invalid",
]


class SessionFacts(BaseModel):
    """What a read-only look found about one directory under `<root>/sessions`."""

    model_config = ConfigDict(frozen=True)
    name: str
    path: str
    name_ok: bool
    family: str = ""
    version: int = 0
    has_wal: bool = False
    segments: int = 0
    wal_bytes: int = 0
    manifest: ManifestStatus = "missing"
    manifest_stale: bool = False
    state: str = ""
    parent: str | None = None
    parent_last_seq: int | None = None
    lock_holder: str = ""
    holder_alive: bool | None = None
    pid_reused: bool = False
    wal: WalStatus = "none"
    wal_detail: str = ""
    tail_bytes: int = 0
    last_seq: int | None = None
    tmp_files: tuple[str, ...] = ()
    orphan_exports: tuple[str, ...] = ()
    not_owned: bool = False
    read_only: bool = False
    snapshots_invalid: int = 0
    snapshots_stale: int = 0
    raw_before_settings: bool = False
    unsupported_format: int | None = None

    @property
    def incomplete(self) -> bool:
        """True when the directory never got a usable first WAL segment."""
        return not self.has_wal or self.segments == 0


def _wal_status(
    wal_dir: Path, deadline: float | None
) -> tuple[WalStatus, str, int, int | None, int | None]:
    """Scan the WAL read-only; return (status, detail, tail bytes, last seq, bad version)."""
    if deadline is not None and time.monotonic() > deadline:
        return ("timeout", "deep time budget used up before this session", 0, None, None)
    res = WalReader.scan(wal_dir)
    if res.is_ok:
        rep = res.danger_ok
        if rep.tail is not None:
            return ("torn-tail", rep.tail.reason, rep.tail.length, rep.last_seq, None)
        return ("ok", "", 0, rep.last_seq, None)
    err = res.danger_err
    if isinstance(err, WalUnsupportedFormat):
        return ("unsupported-format", f"format {err.found}", 0, None, err.found)
    if isinstance(err, WalSegmentHeaderInvalid):
        if err.segment is None:
            return ("none", err.reason, 0, None, None)
        return ("header-invalid", f"segment {err.segment}: {err.reason}", 0, None, None)
    if isinstance(err, WalCorrupt):
        text = f"segment {err.segment} offset {err.offset}: {err.reason}"
        if "seal counts" in err.reason:
            return ("seal-mismatch", text, 0, None, None)
        if "seq gap" in err.reason or "first_seq" in err.reason or "missing segment" in err.reason:
            return ("seq-gap", text, 0, None, None)
        return ("corrupt", text, 0, None, None)
    return ("corrupt", str(err), 0, None, None)


def _leftovers(sdir: Path) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return (tmp-file names, export names lacking a provenance sidecar), read-only."""
    tmp: list[str] = []
    orphans: list[str] = []
    for sub in ("", "snapshots", "exports"):
        base = sdir / sub if sub else sdir
        try:
            entries = sorted(p for p in base.iterdir() if p.is_file())
        except OSError:
            continue
        for p in entries:
            if ".tmp" in p.name:
                tmp.append(f"{sub}/{p.name}" if sub else p.name)
            elif sub == "exports" and not p.name.endswith(PROV_SUFFIX):
                if not (base / (p.name + PROV_SUFFIX)).is_file():
                    orphans.append(p.name)
    return (tuple(tmp), tuple(orphans))


def _owner_flags(sdir: Path) -> tuple[bool, bool]:
    """Return (not owned by the current user, not writable by the current user)."""
    not_owned = hasattr(os, "getuid") and sdir.stat().st_uid != os.getuid()
    return (bool(not_owned), not os.access(sdir, os.W_OK))


def _snapshot_counts(
    sdir: Path, wal_dir: Path, last_seq: int | None, scanned: bool
) -> tuple[int, int]:
    """Return (invalid snapshot files, stale valid snapshots) without touching them."""
    try:
        files = [p for p in snapshot_dir(sdir).glob("snap-*.snap") if p.is_file()]
    except OSError:
        return (0, 0)
    valid = list_snapshots(sdir)
    invalid = len(files) - len(valid)
    if not scanned or not valid:
        return (invalid, 0)
    hashes = prefix_hashes_at(wal_dir, [s.covers_seq for _, s in valid])
    stale = 0
    for _, snap in valid:
        if last_seq is None or snap.covers_seq > last_seq:
            stale += 1
        elif hashes.is_ok and hashes.danger_ok[0].get(snap.covers_seq) != snap.prefix_hash:
            stale += 1
    return (invalid, stale)


def _raw_before_settings(wal_dir: Path) -> bool:
    """True when a RAW_BLOCK record appears before any SETTINGS record (verified prefix only)."""
    for item in WalReader(wal_dir).records():
        if item.is_err:
            return False
        if item.danger_ok.type == RecordType.SETTINGS:
            return False
        if item.danger_ok.type == RecordType.RAW_BLOCK:
            return True
    return False


def _pid_reused(holder: str, alive: bool | None) -> bool:
    """True when the recorded pid is running but is not the process that took the lock."""
    if alive is not False:
        return False
    m = re.search(r"\bpid=(\d+)", holder)
    return bool(m) and proc_start_token(int(m[1])) is not None


def _one(sdir: Path, deep: bool, deadline: float | None) -> SessionFacts:
    """Survey one session directory (never writes)."""
    m = _VER_RE.match(sdir.name)
    wal_dir = sdir / "wal"
    segs = [p for p in wal_dir.iterdir() if _SEG_RE.match(p.name)] if wal_dir.is_dir() else []
    size = sum(p.stat().st_size for p in segs)
    holder, alive = read_lock_holder(sdir)
    mf = read_manifest(sdir)
    manifest = mf.danger_ok if mf.is_ok else None
    status: ManifestStatus = "unparseable" if mf.is_err else ("ok" if manifest else "missing")
    big = size > SKIP_BYTES and not deep
    if not segs:
        wal, detail, tail, last, bad = "none", "", 0, None, None
    elif big:
        wal, detail, tail, last, bad = "skipped", f"{size} bytes (use --deep)", 0, None, None
    else:
        wal, detail, tail, last, bad = _wal_status(wal_dir, deadline if deep else None)
    raw_first = wal in ("ok", "torn-tail") and _raw_before_settings(wal_dir)
    tmp, orphans = _leftovers(sdir)
    not_owned, read_only = _owner_flags(sdir)
    invalid, stale = _snapshot_counts(sdir, wal_dir, last, wal in ("ok", "torn-tail"))
    stale_manifest = manifest is None or (wal in ("ok", "torn-tail") and manifest.last_seq != last)
    return SessionFacts(
        name=sdir.name,
        path=str(sdir),
        name_ok=bool(_NAME_RE.match(sdir.name)),
        family=m["family"] if m else "",
        version=int(m["ver"]) if m else 0,
        has_wal=wal_dir.is_dir(),
        segments=len(segs),
        wal_bytes=size,
        manifest=status,
        manifest_stale=stale_manifest and status != "unparseable",
        state=manifest.state if manifest else "",
        parent=manifest.parent if manifest else None,
        parent_last_seq=manifest.parent_last_seq if manifest else None,
        lock_holder=holder,
        holder_alive=alive,
        pid_reused=_pid_reused(holder, alive),
        wal=wal,
        wal_detail=detail,
        tail_bytes=tail,
        last_seq=last,
        tmp_files=tmp,
        orphan_exports=orphans,
        not_owned=not_owned,
        read_only=read_only,
        snapshots_invalid=invalid,
        snapshots_stale=stale,
        raw_before_settings=raw_first,
        unsupported_format=bad,
    )


def survey_sessions(
    data_root: str, deep: bool = False, timeout_s: float = DEEP_TIMEOUT_S
) -> list[SessionFacts]:
    """Survey every session directory under the data root using read-only store APIs."""
    root = Path(data_root) / SESSIONS_DIRNAME
    try:
        dirs = sorted(p for p in root.iterdir() if p.is_dir())
    except OSError:
        _log.info("no sessions directory at %s", root)
        return []
    deadline = time.monotonic() + timeout_s if deep else None
    found: list[SessionFacts] = []
    for sdir in dirs:
        try:
            found.append(_one(sdir, deep, deadline))
        except OSError as exc:
            _log.warning("could not survey %s: %s", sdir, exc)
    _log.info("surveyed %d session directories (deep=%s)", len(found), deep)
    return found
