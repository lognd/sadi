"""Kill a writer subprocess mid-write (SIGKILL / TerminateProcess) and prove DS1 holds."""

# frob:ticket 01M6W7R2ZMZSCRWKCRFHAH4MTB
from __future__ import annotations

import logging
import os
import random
from pathlib import Path

import pytest

from sadi.store.wal import WalReader

from . import harness

_log = logging.getLogger("sadi.tests.crash")

ITERATIONS = int(os.environ.get("SADI_CRASH_ITERATIONS", "8"))
FP_RUNS = int(os.environ.get("SADI_CRASH_FP_RUNS", "1"))

# Every failpoint the store places on a write path that the crashee exercises.
FAILPOINTS = (
    "session.mkdir.before",
    "session.lock.after",
    "session.manifest.write",
    "session.manifest.before_replace",
    "wal.encode.before",
    "wal.write.partial",
    "wal.write.after",
    "wal.fsync.before",
    "wal.fsync.after",
    "wal.publish.after",
    "wal.rotate.after_seal_write",
    "wal.rotate.after_seal_fsync",
    "wal.rotate.after_create",
    "wal.rotate.after_header",
    "wal.rotate.after_header_fsync",
    "wal.rotate.after_dir_fsync",
    "snapshot.write",
    "snapshot.fsync",
    "snapshot.rename",
    "snapshot.dirsync",
    "snapshot.ref",
    "durable.write",
    "durable.fsync_file",
    "durable.rename",
)


def _seg_bytes(seed: int) -> int:
    """Alternate tiny segments (rotation churn) with one big segment (snapshot churn)."""
    return harness.SEG_BYTES if seed % 2 else harness.BIG_SEG_BYTES


def _assert_clean(run: harness.Run, name: str) -> None:
    """Fail with the violation list (and save an artifact) if recovery broke an invariant."""
    problems = harness.verify_recovery(run)
    if problems:
        harness.save_artifact(run, name)
    assert not problems, f"{name} (seed {run.seed}): {problems}"


# frob:tests python/sadi/store/wal.py::WalWriter.append_batch
# frob:tests python/sadi/store/wal.py::WalReader.records
# frob:tests python/sadi/store/wal.py::WalReader.scan
# frob:tests python/tests/crash/harness.py::verify_recovery
@pytest.mark.parametrize("seed", range(ITERATIONS))
def test_random_kill_recovers(tmp_path: Path, seed: int) -> None:
    """Kill at a random moment after the first ack; DS1 invariants hold on recovery."""
    rng = random.Random(seed)
    run = harness.run_crashee(
        tmp_path, seed, kill_delay_s=rng.uniform(0.0, 0.6), seg_bytes=_seg_bytes(seed)
    )
    _assert_clean(run, f"random-{seed}")


# frob:tests python/sadi/store/wal.py::WalWriter.append_batch
# frob:tests python/sadi/store/wal.py::WalReader.scan
# frob:tests python/tests/crash/harness.py::verify_recovery
@pytest.mark.parametrize("run_no", range(FP_RUNS))
@pytest.mark.parametrize("name", FAILPOINTS)
def test_failpoint_kill_recovers(tmp_path: Path, name: str, run_no: int) -> None:
    """Die inside every write-path failpoint (at its nth hit); recovery is clean."""
    nth = 1 + (run_no * 2) % 5
    run = harness.run_crashee(
        tmp_path,
        1000 + run_no,
        failpoints=f"{name}=nth:{nth}:kill",
        seg_bytes=harness.SEG_BYTES if name.startswith("wal.rotate") else harness.BIG_SEG_BYTES,
    )
    # Some failpoints sit on paths a given nth may never reach; a clean exit is also valid.
    assert run.returncode in (137, 0), f"unexpected exit {run.returncode}"
    _assert_clean(run, f"fp-{name}-{run_no}")


# frob:tests python/sadi/store/wal.py::WalReader.scan
# frob:tests python/tests/crash/harness.py::verify_recovery
def test_partial_record_is_torn_tail_not_corruption(tmp_path: Path) -> None:
    """Dying between the two halves of a batch write leaves a torn tail the reader reports."""
    run = harness.run_crashee(
        tmp_path, 7, failpoints="wal.write.partial=nth:3:kill", seg_bytes=harness.BIG_SEG_BYTES
    )
    assert run.returncode == 137
    sdir = harness.session_dirs(run.root)[0]
    scan = WalReader.scan(sdir / "wal")
    scan.unwrap()
    assert scan.danger_ok.tail is not None
    assert scan.danger_ok.last_seq is not None
    assert scan.danger_ok.last_seq >= run.oracle.max_ack
    _assert_clean(run, "partial-record")


# frob:tests python/sadi/store/session.py::resume_session
def test_stale_lock_is_never_broken_silently(tmp_path: Path) -> None:
    """After a kill the leftover data-root lock is reported; only explicit recovery proceeds."""
    from sadi.store.session import RootLockFailed, resume_session  # noqa: PLC0415

    run = harness.run_crashee(
        tmp_path, 11, failpoints="wal.fsync.after=nth:4:kill", seg_bytes=harness.BIG_SEG_BYTES
    )
    assert run.returncode == 137
    sdir = harness.session_dirs(run.root)[0]
    before = harness.tree_digest(sdir)
    refused = resume_session(sdir)
    assert refused.is_err
    assert isinstance(refused.danger_err, RootLockFailed)
    assert harness.tree_digest(sdir) == before
    assert len(harness.session_dirs(run.root)) == 1


# frob:tests python/sadi/store/wal.py::WalReader.records
# frob:tests python/sadi/store/events.py::recover_state
@pytest.mark.parametrize("seed", range(max(4, ITERATIONS // 2)))
def test_power_loss_truncation_recovers(tmp_path: Path, seed: int) -> None:
    """Truncate to the last fsynced offset plus garbage: acked records survive, tail is torn."""
    rng = random.Random(5000 + seed)
    run = harness.run_crashee(
        tmp_path / "live", seed, kill_delay_s=rng.uniform(0.0, 0.6), seg_bytes=_seg_bytes(seed)
    )
    if not harness.session_dirs(run.root):
        pytest.skip("killed before the session existed")
    lossy = harness.power_loss_copy(run, tmp_path / "lossy", rng)
    _assert_clean(lossy, f"power-loss-{seed}")
