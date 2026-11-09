"""Crash harness: spawn the crashee, kill it, then check the DS1 invariants on what is left."""

# frob:ticket 01M6W7R2ZMZSCRWKCRFHAH4MTB
from __future__ import annotations

import hashlib
import logging
import os
import random
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sadi.store import events, snapshot
from sadi.store.lock import LOCK_FILENAME, LockHeld
from sadi.store.manifest import read_manifest
from sadi.store.records import RecordType
from sadi.store.session import RootLockFailed, open_readonly, resume_session
from sadi.store.wal import SEGMENT_HEADER_LEN, ScanReport, WalReader

from .crashee import block_packets, block_payload

_log = logging.getLogger("sadi.tests.crash.harness")

CRASHEE = Path(__file__).with_name("crashee.py")
ARTIFACT_ENV = "SADI_CRASH_ARTIFACTS"
SEG_BYTES = 6000
BIG_SEG_BYTES = 1 << 20
MAX_RECORDS = 60
RETRY_BUDGET_S = 15.0
RETRY_FIRST_DELAY_S = 0.01
RETRY_MAX_DELAY_S = 0.25
LOCK_NAME = "lock"


@dataclass
class Oracle:
    """What the crashee promised before it died (parsed from its oracle log)."""

    started: Path | None = None
    max_ack: int = 0
    snapshots: dict[str, str] = field(default_factory=dict)
    fsync_offsets: dict[str, int] = field(default_factory=dict)
    clean_exit: bool = False


@dataclass
class Run:
    """One crashee execution: where it wrote and how it ended."""

    root: Path
    oracle_path: Path
    seed: int
    returncode: int
    oracle: Oracle
    seg_bytes: int = SEG_BYTES


def parse_oracle(path: Path) -> Oracle:
    """Parse the oracle log; a torn final line (no newline) is dropped."""
    out = Oracle()
    if not path.exists():
        return out
    text = path.read_bytes().decode("ascii", errors="replace")
    lines = text.split("\n")[:-1]
    for line in lines:
        parts = line.split(" ")
        if parts[0] == "started":
            out.started = Path(" ".join(parts[1:]))
        elif parts[0] == "ack":
            out.max_ack = max(out.max_ack, int(parts[1]))
        elif parts[0] == "snapshot":
            out.snapshots[parts[1]] = parts[2]
        elif parts[0] == "fsync_offset":
            out.fsync_offsets[parts[1]] = int(parts[2])
        elif parts[0] == "clean_exit":
            out.clean_exit = True
    return out


def _spawn(
    root: Path, oracle: Path, seed: int, seg_bytes: int, env_extra: dict[str, str]
) -> subprocess.Popen[bytes]:
    """Start the crashee with `sadi` importable and the given extra environment."""
    env = dict(os.environ)
    pkg_root = str(Path(__file__).resolve().parents[2])
    env["PYTHONPATH"] = pkg_root + os.pathsep + env.get("PYTHONPATH", "")
    env.update(env_extra)
    cmd = [sys.executable, str(CRASHEE), str(root), str(oracle), str(seed)]
    cmd += [str(MAX_RECORDS), str(seg_bytes)]
    return subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def run_crashee(
    workdir: Path,
    seed: int,
    *,
    failpoints: str | None = None,
    kill_delay_s: float | None = None,
    seg_bytes: int = SEG_BYTES,
    timeout_s: float = 60.0,
) -> Run:
    """Run the crashee to a failpoint kill, or SIGKILL it `kill_delay_s` after its first ack."""
    root = workdir / "root"
    root.mkdir(parents=True, exist_ok=True)
    oracle_path = workdir / "oracle.log"
    env = {"SADI_FAILPOINTS": failpoints} if failpoints is not None else {}
    proc = _spawn(root, oracle_path, seed, seg_bytes, env)
    if kill_delay_s is not None:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline and proc.poll() is None:
            if parse_oracle(oracle_path).max_ack >= 1:
                break
            time.sleep(0.005)
        time.sleep(kill_delay_s)
        if proc.poll() is None:
            proc.kill()
            _log.info("seed %d: killed after %.3fs", seed, kill_delay_s)
    try:
        rc = proc.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        proc.kill()
        rc = proc.wait()
    oracle = parse_oracle(oracle_path)
    _log.info("seed %d: rc=%d max_ack=%d", seed, rc, oracle.max_ack)
    return Run(root, oracle_path, seed, rc, oracle, seg_bytes)


# frob:ticket 01M703DQWZ3TFQ5FXAKVYZ1DZT
def _read_bytes_retry(path: Path) -> bytes:
    """Read `path`, retrying PermissionError with bounded backoff (Windows replace/AV windows)."""
    deadline = time.monotonic() + RETRY_BUDGET_S
    delay = RETRY_FIRST_DELAY_S
    while True:
        try:
            return path.read_bytes()
        except PermissionError:
            if time.monotonic() >= deadline:
                raise
            _log.warning("read of %s denied; retrying in %.3fs", path, delay)
            time.sleep(delay)
            delay = min(delay * 2, RETRY_MAX_DELAY_S)


def tree_digest(root: Path) -> str:
    """Hash every relative path and file content under `root` (mtimes excluded)."""
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        h.update(f"{p.relative_to(root).as_posix()}|{p.is_dir()}\n".encode())
        if p.is_file():
            # frob:ticket 01M700BKTA0N0NYKWBDG24R9GM
            # A held lock file cannot be read on Windows (byte-range lock);
            # its size still catches any silent rewrite.
            h.update(
                str(p.stat().st_size).encode() if p.name == LOCK_NAME else _read_bytes_retry(p)
            )
    return h.hexdigest()


def session_dirs(root: Path) -> list[Path]:
    """Return the version directories under `<root>/sessions`."""
    base = root / "sessions"
    return sorted(p for p in base.iterdir() if p.is_dir()) if base.is_dir() else []


def _check_records(sdir: Path, run: Run, report: ScanReport | None, out: list[str]) -> None:
    """I1, I2, I3: the recovered records are exactly 1..N, cover every ack, match the generator."""
    seqs: list[int] = []
    for item in WalReader(sdir / "wal").records():
        if item.is_err:
            out.append(f"I3: reader error {item.danger_err}")
            return
        rec = item.danger_ok
        seqs.append(rec.seq)
        ordinal = len(seqs)  # logical index: SEAL seqs are not yielded
        if rec.type == RecordType.RAW_BLOCK:
            want = block_payload(run.seed, ordinal, block_packets(ordinal))
            if rec.payload != want:
                out.append(f"I3: RAW_BLOCK payload mismatch at seq {rec.seq}")
    # SEAL records consume a seq but are not data records, so the only legal gaps are the
    # seq right after each sealed segment's last data record.
    seal_seqs = (
        {(s.last_seq or 0) + 1 for s in report.segments if s.sealed and (s.last_seq or 0) > 0}
        if report
        else set()
    )
    top = seqs[-1] if seqs else 0
    expect = [n for n in range(1, top + 1) if n not in seal_seqs]
    if seqs != expect:
        out.append(f"I1: recovered seqs are not a gapless prefix: {seqs[:5]}...{seqs[-5:]}")
    if top < run.oracle.max_ack:
        out.append(f"I2: acknowledged {run.oracle.max_ack} but recovered only up to {top}")
    if report is not None and report.last_seq != (seqs[-1] if seqs else None):
        out.append("I1: scan last_seq disagrees with iteration")


def _check_snapshots(sdir: Path, run: Run, out: list[str]) -> None:
    """I4, I5: every committed snapshot is intact and unchanged; none at a final path is torn."""
    snaps = snapshot.snapshot_dir(sdir)
    finals = sorted(snaps.glob("snap-*.snap")) if snaps.is_dir() else []
    valid = {p for p, _ in snapshot.list_snapshots(sdir)}
    for p in finals:
        if p not in valid:
            out.append(f"I5: torn or invalid snapshot at final path {p.name}")
    for name, digest in run.oracle.snapshots.items():
        path = snaps / name
        if not path.exists():
            out.append(f"I4: committed snapshot {name} vanished")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            out.append(f"I4: committed snapshot {name} changed")
    latest = snapshot.load_latest_snapshot(sdir)
    if latest.is_err:
        out.append(f"I5: load_latest_snapshot failed: {latest.danger_err}")


def _check_state(sdir: Path, out: list[str]) -> None:
    """I7, I10: replay is deterministic and snapshot-assisted recovery equals full replay."""
    first = events.recover_state(sdir)
    second = events.recover_state(sdir)
    full = events.replay_wal(sdir / "wal")
    if first.is_err or second.is_err or full.is_err:
        out.append(f"I10: replay failed: {first} {second} {full}")
        return
    if first.danger_ok.model_dump_json() != second.danger_ok.model_dump_json():
        out.append("I10: two replays differ")
    if first.danger_ok.model_dump_json() != full.danger_ok.model_dump_json():
        out.append("I7: snapshot-assisted recovery differs from full replay")


def verify_recovery(run: Run, *, check_resume: bool = True) -> list[str]:
    """Return every DS1 violation found in the session left by `run` (empty means clean)."""
    out: list[str] = []
    dirs = session_dirs(run.root)
    if not dirs:
        if run.oracle.max_ack:
            out.append("I2: acknowledged records but no session directory")
        return out
    if len(dirs) != 1:
        out.append(f"I4: expected one session dir, found {[d.name for d in dirs]}")
        return out
    sdir = dirs[0]
    before = tree_digest(sdir)
    segs = sorted((sdir / "wal").glob("seg-*.wal")) if (sdir / "wal").is_dir() else []
    report: ScanReport | None = None
    if segs:
        scan = WalReader.scan(sdir / "wal")
        torn_first_header = (
            run.oracle.max_ack == 0 and len(segs) == 1 and segs[0].stat().st_size < 64
        )
        if scan.is_err and torn_first_header:
            # Nothing was acked, so a torn first segment header loses no data (see ~RGHGDN9).
            _log.warning("tolerating torn first segment header with zero acks")
            return out
        if scan.is_err:
            out.append(f"I3: scan reported {scan.danger_err}")
        else:
            report = scan.danger_ok
        _check_records(sdir, run, report, out)
        _check_snapshots(sdir, run, out)
        # frob:ticket 01M6WK6V5B6CH2T7GVSS2SQ33J
        # Replay-equivalence runs on rotated WALs too.
        _check_state(sdir, out)
    elif run.oracle.max_ack:
        out.append("I2: acknowledged records but no segment files")
    manifest = _read_manifest_retry(sdir)
    if manifest.is_err:
        out.append(f"I5: manifest torn or invalid: {manifest.danger_err}")
    ro = open_readonly(sdir)
    if ro.is_err:
        out.append(f"open_readonly failed: {ro.danger_err}")
    if tree_digest(sdir) != before:
        out.append("I8: read-only recovery modified the session directory")
    if check_resume and segs and not out:
        out.extend(_check_resume(sdir, before))
    return out


# frob:ticket 01M703DQWZ3TFQ5FXAKVYZ1DZT
def _read_manifest_retry(sdir: Path) -> Any:
    """read_manifest, retried while the OS denies access (killed writer's handle not yet gone)."""
    deadline = time.monotonic() + RETRY_BUDGET_S
    delay = RETRY_FIRST_DELAY_S
    while True:
        got = read_manifest(sdir)
        if got.is_ok or "denied" not in str(got.danger_err).lower() or time.monotonic() >= deadline:
            return got
        time.sleep(delay)
        delay = min(delay * 2, RETRY_MAX_DELAY_S)


# frob:ticket 01M703DQWZ3TFQ5FXAKVYZ1DZT
def _resume_waiting_for_lock(sdir: Path, *, recover_stale: bool) -> Any:
    """resume_session, polling with bounded backoff while the OS still reports the lock held.

    Windows frees a killed process's byte-range lock lazily; a lock that stays held past the
    budget is still reported as LockHeld, never broken.
    """
    deadline = time.monotonic() + RETRY_BUDGET_S
    delay = RETRY_FIRST_DELAY_S
    while True:
        got = resume_session(sdir, recover_stale=recover_stale)
        held = (
            got.is_err
            and isinstance(got.danger_err, RootLockFailed)
            and isinstance(got.danger_err.error, LockHeld)
        )
        if not held or time.monotonic() >= deadline:
            return got
        _log.warning("data-root lock still held; retrying in %.3fs", delay)
        time.sleep(delay)
        delay = min(delay * 2, RETRY_MAX_DELAY_S)


def _check_resume(sdir: Path, before: str) -> list[str]:
    """Resume as a new version; the stale lock must be reported, never silently broken."""
    out: list[str] = []
    refused = _resume_waiting_for_lock(sdir, recover_stale=False)
    if refused.is_ok:
        refused.danger_ok.close()
    resumed = refused if refused.is_ok else _resume_waiting_for_lock(sdir, recover_stale=True)
    if resumed.is_err:
        out.append(f"resume failed even with recover_stale: {resumed.danger_err}")
        return out
    resumed.danger_ok.close()
    if tree_digest(sdir) != before:
        out.append("I4: resume modified the parent version")
    if len(session_dirs(sdir.parent.parent)) != 2:
        out.append("I4: resume did not create exactly one new version directory")
    return out


def power_loss_copy(run: Run, dest_root: Path, rng: random.Random) -> Run:
    """Copy the session, cut the last segment to its last fsynced offset, append garbage."""
    src = session_dirs(run.root)[0]
    dest = dest_root / "sessions" / src.name
    # frob:ticket 01M700BKTA0N0NYKWBDG24R9GM
    # Skip the lock file: byte-range locked on Windows and not WAL/snapshot data.
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns(LOCK_NAME))
    segs = sorted((dest / "wal").glob("seg-*.wal"))
    if segs:
        last = segs[-1]
        keep = run.oracle.fsync_offsets.get(last.name, SEGMENT_HEADER_LEN)
        with last.open("r+b") as fh:
            fh.truncate(min(keep, last.stat().st_size))
            fh.seek(0, os.SEEK_END)
            kept = fh.tell()
            junk = rng.randint(0, 4096)
            if kept < SEGMENT_HEADER_LEN:
                # frob:ticket 01M701SFR4E1BKBXW1RCN14TK3
                # The writer fsyncs a segment header before any record can be acked into the
                # segment, so a cut inside the header models a torn header (<= 64 bytes); a full
                # garbage "header" would be arbitrary corruption, not power loss.
                junk = min(junk, SEGMENT_HEADER_LEN - kept)
            fh.write(rng.randbytes(junk))
    return Run(dest_root, run.oracle_path, run.seed, run.returncode, run.oracle, run.seg_bytes)


def save_artifact(run: Run, name: str) -> None:
    """Copy the failing run (session root and oracle) under $SADI_CRASH_ARTIFACTS if set."""
    target = os.environ.get(ARTIFACT_ENV)
    if target is None or target == "":
        return
    dest = Path(target) / name
    # frob:ticket 01M701SFR4E1BKBXW1RCN14TK3
    # Lock files may still be byte-range locked (Windows WinError 33) and carry no evidence.
    shutil.copytree(
        run.root,
        dest / "root",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns(LOCK_NAME, LOCK_FILENAME),
    )
    if run.oracle_path.exists():
        shutil.copy2(run.oracle_path, dest / "oracle.log")
    _log.error("saved failing run to %s", dest)
