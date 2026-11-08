"""Writer races: slow fsync with a full queue, cancel during a write, lock-order checks."""

# frob:ticket 01M6W7RAY4KTF866Q0Y7B4SZGG
from __future__ import annotations

import threading
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from typani import Ok

from sadi.jobs import JobId
from sadi.jobs.testing import JobHarness, Step, make_spec
from sadi.logging_setup import get_logger
from sadi.store import failpoints
from sadi.store.records import MarkerV1, NewRecord, RecordType, json_record
from sadi.store.wal import WalConfig, WalReader
from sadi.store.writer_thread import Backpressure, WriterHandle

from .tracing import LockTracer, TracedLock, run_with_deadline

_log = get_logger("tests.concurrency.writer_races")

SID = uuid.UUID(int=0x5AD1)


@pytest.fixture(autouse=True)
def _reset_failpoints() -> Iterator[None]:
    """Never leak failpoints between tests."""
    failpoints.clear()
    yield
    failpoints.clear()


def _marker(i: int) -> NewRecord:
    """A small, ordered, self-describing record."""
    return json_record(RecordType.MARKER, MarkerV1(kind="mark", label=f"m{i}", raw_seq=i))


def _open(tmp_path: Path, config: WalConfig) -> WriterHandle:
    """Open a writer handle in a fresh wal dir."""
    (tmp_path / "wal").mkdir()
    opened = WriterHandle.open(tmp_path / "wal", SID, 1, config)
    return opened.unwrap()


def _produce(handle: WriterHandle, count: int, seqs: list[int]) -> None:
    """Submit `count` records, retrying on Backpressure (the record is never dropped)."""
    for i in range(count):
        rec = _marker(i)
        while True:
            res = handle.submit(rec)
            if res.is_ok:
                seqs.append(res.danger_ok)
                break
            assert isinstance(res.danger_err, Backpressure), res.danger_err


# frob:tests python/sadi/store/writer_thread.py::WriterHandle.submit
# frob:tests python/sadi/store/writer_thread.py::WriterHandle.wait_durable
def test_slow_fsync_with_full_queue_loses_nothing(tmp_path: Path) -> None:
    """A slow disk exerts backpressure but every record is eventually durable, in order."""
    cfg = WalConfig(queue_max_items=4, submit_timeout_s=0.05)
    handle = _open(tmp_path, cfg)
    failpoints.configure({"wal.fsync.before": "sleep:60"})
    seqs: list[int] = []
    count = 40
    run_with_deadline(lambda: _produce(handle, count, seqs), 60.0, "slow-fsync producer")
    assert seqs == sorted(seqs)
    assert len(set(seqs)) == count
    assert handle.wait_durable(seqs[-1], 30.0) == Ok(None)
    assert handle.metrics().backpressure_events > 0
    assert handle.close().is_ok
    report = WalReader.scan(tmp_path / "wal").danger_ok
    assert report.tail is None
    assert report.record_count >= count


# frob:tests python/sadi/jobs/manager.py::JobManager.cancel
# frob:tests python/sadi/store/writer_thread.py::WriterHandle.enqueued_seq
def test_cancel_during_write_does_not_block_or_lose(tmp_path: Path) -> None:
    """Cancelling a job while a WAL batch is mid-fsync neither blocks nor loses the batch."""
    handle = _open(tmp_path, WalConfig())
    failpoints.configure({"wal.fsync.before": "sleep:300"})
    h = JobHarness(1)

    def script(inputs: dict[str, object]):  # type: ignore[no-untyped-def]
        while True:
            cancelled = yield Step(fraction=0.1)
            if cancelled:
                return {}

    h.register("spin", script)
    h.start()
    try:
        spec = make_spec(1, "a", "spin")
        assert isinstance(h.manager.submit(spec), Ok)
        seq = handle.submit(_marker(0)).danger_ok
        # The fsync failpoint holds the batch: enqueued is ahead of durable right now.
        assert handle.enqueued_seq >= seq > handle.durable_seq
        # The manager is loop-thread only, so cancel runs here; it must return while the
        # writer thread is still sleeping in fsync (a blocking cancel would stall for 300 ms+).
        assert isinstance(h.manager.cancel(JobId(spec.job_id)), Ok)
        assert handle.durable_seq < seq, "cancel returned only after the batch became durable"
        assert handle.wait_durable(seq, 30.0) == Ok(None)
        assert handle.close().is_ok
    finally:
        h.close()
    assert WalReader.scan(tmp_path / "wal").danger_ok.record_count >= 1


def _traced(handle: WriterHandle, tracer: LockTracer) -> None:
    """Swap the handle's leaf lock for an L3 traced lock."""
    handle._lock = TracedLock(3, "WriterHandle._lock", tracer)  # type: ignore[assignment]  # ty: ignore[invalid-assignment]


# frob:tests python/tests/concurrency/tracing.py::LockTracer.on_acquire
# frob:tests python/sadi/store/writer_thread.py::WriterHandle.metrics
def test_writer_lock_order_under_contention(tmp_path: Path) -> None:
    """Producers, a metrics poller and a waiter never nest locks against the L1<L2<L3 order."""
    tracer = LockTracer()
    handle = _open(tmp_path, WalConfig())
    _traced(handle, tracer)
    stop = threading.Event()

    def poll() -> None:
        while not stop.is_set():
            handle.metrics()
            _ = handle.durable_seq
            handle.check_health()

    poller = threading.Thread(target=poll, daemon=True)
    poller.start()
    seqs: list[list[int]] = [[] for _ in range(3)]
    threads = [
        threading.Thread(target=_produce, args=(handle, 50, seqs[i]), daemon=True) for i in range(3)
    ]
    for t in threads:
        t.start()

    def join_all() -> None:
        for t in threads:
            t.join()

    run_with_deadline(join_all, 60.0, "lock-order producers")
    stop.set()
    poller.join(10.0)
    last = max(max(s) for s in seqs)
    assert handle.wait_durable(last, 30.0) == Ok(None)
    assert handle.close().is_ok
    assert tracer.acquires > 0
    assert tracer.violations == []


# frob:tests python/tests/concurrency/tracing.py::TracedLock
def test_tracer_detects_an_inversion() -> None:
    """Positive control: acquiring L2 while holding L3 is reported (sequentially, no deadlock)."""
    tracer = LockTracer()
    leaf = TracedLock(3, "leaf", tracer)
    acq = TracedLock(2, "acq", tracer)
    with leaf, acq:
        pass
    assert len(tracer.violations) == 1
