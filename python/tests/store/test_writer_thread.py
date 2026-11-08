"""Tests for the WAL writer-thread facade: backpressure, metrics, stall, shutdown, faults."""

from __future__ import annotations

import errno
import threading
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from sadi.store import durable, failpoints
from sadi.store.durable import DurableIo
from sadi.store.records import NewRecord, RecordType
from sadi.store.wal import (
    WalClosed,
    WalConfig,
    WalDurable,
    WalFailed,
    WalInternal,
    WalInvalidRecord,
    WalReader,
    WalTimeout,
)
from sadi.store.writer_thread import (
    Backpressure,
    Closed,
    DiskFull,
    Internal,
    InvalidRecord,
    IoError,
    Stalled,
    WriterError,
    WriterHandle,
    WriterState,
    _Ring,
    map_wal_error,
)

SESSION = uuid.UUID(int=0x5AD2)
WAIT_S = 10.0


@pytest.fixture(autouse=True)
def _reset() -> Iterator[None]:
    """Clear failpoints around each test."""
    failpoints.clear()
    yield
    failpoints.clear()


class _FakeClock:
    """Manually advanced monotonic clock so stall tests need no sleeping."""

    def __init__(self) -> None:
        """Start at t=0."""
        self.now = 0.0

    def __call__(self) -> float:
        """Return the current fake time."""
        return self.now


class _Gate:
    """Replaces fsync_file: blocks every call until released, signalling when one is entered."""

    def __init__(self, real: Callable[[int], object]) -> None:
        """Wrap the real fsync so released calls still sync."""
        self.real = real
        self.entered = threading.Event()
        self.release = threading.Event()

    def __call__(self, fd: int) -> object:
        """Signal entry, wait for release, then fsync for real."""
        self.entered.set()
        assert self.release.wait(WAIT_S)
        return self.real(fd)


def _open(tmp_path: Path, **kw: object) -> WriterHandle:
    """Open a handle in tmp_path/wal; WalConfig fields and handle kwargs are split by name."""
    wal = tmp_path / "wal"
    wal.mkdir(exist_ok=True)
    handle_kw = {k: v for k, v in kw.items() if k in ("stall_timeout_s", "clock")}
    cfg = {k: v for k, v in kw.items() if k not in handle_kw}
    res = WriterHandle.open(wal, SESSION, 1, WalConfig(**cfg), **handle_kw)  # type: ignore[arg-type]
    assert res.is_ok, res
    return res.danger_ok


def _rec(n: int, size: int = 16) -> NewRecord:
    """Build a small NOTE record whose payload identifies `n`."""
    return NewRecord(type=int(RecordType.NOTE), payload=bytes([n % 256]) * size)


def _payloads(tmp_path: Path) -> list[bytes]:
    """Return payloads of all verified records on disk."""
    return [r.danger_ok.payload for r in WalReader(tmp_path / "wal").records() if r.is_ok]


def _gate_fsync(monkeypatch: pytest.MonkeyPatch) -> _Gate:
    """Install a blocking fsync gate (call after the handle is open)."""
    gate = _Gate(durable.fsync_file)
    monkeypatch.setattr(durable, "fsync_file", gate)
    return gate


# frob:ticket 01M6W7R2DCY0H5XQ9F53F2W55E
# frob:tests python/sadi/store/writer_thread.py::WriterHandle.submit
# frob:tests python/sadi/store/writer_thread.py::WriterHandle.metrics
def test_submit_assigns_dense_seq_and_metrics_track_durability(tmp_path: Path) -> None:
    """Seqs are dense in submit order; durable gate and metrics reflect fsync."""
    h = _open(tmp_path)
    seqs = [h.submit(_rec(i)).danger_ok for i in range(5)]
    assert seqs == [1, 2, 3, 4, 5]
    assert h.wait_durable(5, WAIT_S).is_ok
    m = h.metrics()
    assert m.state is WriterState.RUNNING
    assert m.durable_seq == m.enqueued_seq == 5
    assert m.fsync_latency.count >= 1
    assert 0.0 <= m.fsync_latency.p50_ms <= m.fsync_latency.p99_ms
    assert m.submit_wait.count == 5
    assert m.free_bytes is not None
    assert m.error is None
    assert h.close().is_ok
    assert _payloads(tmp_path) == [bytes([i]) * 16 for i in range(5)]


# frob:ticket 01M6W7R2DCY0H5XQ9F53F2W55E
# frob:tests python/sadi/store/writer_thread.py::WriterHandle.submit
def test_slow_fsync_applies_backpressure_and_never_drops(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With fsync stalled the full queue reports Backpressure; every accepted record lands."""
    h = _open(tmp_path, queue_max_items=1, submit_timeout_s=0.05)
    gate = _gate_fsync(monkeypatch)
    assert h.submit(_rec(1)).danger_ok == 1
    assert gate.entered.wait(WAIT_S)  # record 1 is inside the slow fsync
    assert h.submit(_rec(2)).danger_ok == 2  # fills the one-slot queue
    refused = h.submit(_rec(3))
    assert refused.is_err
    err = refused.danger_err
    assert isinstance(err, Backpressure)
    assert err.queue_depth_items == 1
    again = h.submit(_rec(3))
    assert isinstance(again.danger_err, Backpressure)
    m = h.metrics()
    assert m.backpressure_events == 2
    assert m.queue_depth_items == 1
    assert m.durable_seq == 0
    assert m.enqueued_seq == 2  # refused records consumed no seq
    gate.release.set()
    assert h.wait_durable(2, WAIT_S).is_ok
    retry = h.submit(_rec(3))  # caller still holds the record and retries: no gap
    assert retry.danger_ok == 3
    assert h.close().is_ok
    assert _payloads(tmp_path) == [bytes([i]) * 16 for i in (1, 2, 3)]


# frob:ticket 01M6W7R2DCY0H5XQ9F53F2W55E
# frob:tests python/sadi/store/writer_thread.py::WriterHandle.check_health
def test_stall_detected_without_progress_and_clears_on_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No durable progress past the timeout reports Stalled; progress clears it."""
    clock = _FakeClock()
    h = _open(tmp_path, stall_timeout_s=5.0, clock=clock)
    gate = _gate_fsync(monkeypatch)
    assert h.check_health().is_ok  # nothing outstanding
    assert h.submit(_rec(1)).is_ok
    assert gate.entered.wait(WAIT_S)
    clock.now = 4.0
    assert h.check_health().is_ok
    clock.now = 6.0
    stalled = h.check_health()
    assert isinstance(stalled.danger_err, Stalled)
    assert stalled.danger_err.enqueued_seq == 1
    assert stalled.danger_err.durable_seq == 0
    assert h.metrics().state is WriterState.STALLED
    gate.release.set()
    assert h.wait_durable(1, WAIT_S).is_ok
    assert h.check_health().is_ok
    assert h.metrics().state is WriterState.RUNNING
    assert h.close().is_ok


# frob:ticket 01M6W7R2DCY0H5XQ9F53F2W55E
# frob:tests python/sadi/store/writer_thread.py::WriterHandle.wait_durable
def test_wait_durable_timeout_is_stalled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A durability wait that times out returns a typed Stalled carrying the seqs."""
    h = _open(tmp_path)
    gate = _gate_fsync(monkeypatch)
    assert h.submit(_rec(1)).is_ok
    assert gate.entered.wait(WAIT_S)
    res = h.wait_durable(1, 0.01)
    assert isinstance(res.danger_err, Stalled)
    assert res.danger_err.enqueued_seq == 1
    gate.release.set()
    assert h.close().is_ok


# frob:ticket 01M6W7R2DCY0H5XQ9F53F2W55E
# frob:tests python/sadi/store/writer_thread.py::WriterHandle.on_failure
# frob:tests python/sadi/store/writer_thread.py::map_wal_error
@pytest.mark.parametrize(
    ("point", "action", "expected"),
    [
        ("wal.write.partial", f"once:error:{errno.ENOSPC}", DiskFull),
        ("wal.write.after", f"once:error:{errno.ENOSPC}", DiskFull),
        ("wal.fsync.before", f"once:error:{errno.ENOSPC}", DiskFull),
        ("wal.fsync.before", f"once:error:{errno.EIO}", IoError),
    ],
)
def test_disk_errors_fail_loudly_and_keep_records(
    tmp_path: Path, point: str, action: str, expected: type[WriterError]
) -> None:
    """ENOSPC/EIO stop the writer with a typed error; waiters, listeners and submits all see it."""
    h = _open(tmp_path)
    seen: list[WriterError] = []
    fired = threading.Event()

    def listener(err: WriterError) -> None:
        """Record the failure and signal the test."""
        seen.append(err)
        fired.set()

    h.on_failure(listener)
    assert h.submit(_rec(1)).is_ok
    assert h.wait_durable(1, WAIT_S).is_ok
    failpoints.configure({point: action})
    assert h.submit(_rec(2)).danger_ok == 2
    waited = h.wait_durable(2, WAIT_S)
    assert isinstance(waited.danger_err, expected)
    assert fired.wait(WAIT_S)
    assert len(seen) == 1
    assert isinstance(seen[0], expected)
    m = h.metrics()
    assert m.state is WriterState.FAILED
    assert isinstance(m.error, expected)
    assert m.durable_seq == 1  # the failed batch is never claimed durable
    assert h.undurable_count() == 1  # and is kept in memory
    assert isinstance(h.submit(_rec(3)).danger_err, expected)
    assert isinstance(h.check_health().danger_err, expected)
    assert isinstance(h.close().danger_err, expected)


# frob:ticket 01M6W7R2DCY0H5XQ9F53F2W55E
# frob:tests python/sadi/store/writer_thread.py::WriterHandle.on_failure
def test_listener_registered_after_failure_runs_immediately(tmp_path: Path) -> None:
    """A late failure listener is invoked at once with the stored typed error."""
    h = _open(tmp_path)
    failpoints.configure({"wal.fsync.before": f"once:error:{errno.ENOSPC}"})
    assert h.submit(_rec(1)).is_ok
    assert isinstance(h.wait_durable(1, WAIT_S).danger_err, DiskFull)
    got: list[WriterError] = []
    h.on_failure(got.append)
    assert len(got) == 1
    assert isinstance(got[0], DiskFull)
    h.close()


# frob:ticket 01M6W7R2DCY0H5XQ9F53F2W55E
# frob:tests python/sadi/store/writer_thread.py::WriterHandle.close
# frob:tests python/sadi/store/writer_thread.py::WriterHandle.enqueued_seq
def test_close_drains_queue_and_writes_final_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Close with a stalled queue still writes every record, then the final one, in order."""
    h = _open(tmp_path, batch_max_records=4)
    gate = _gate_fsync(monkeypatch)
    for i in range(40):
        assert h.submit(_rec(i)).danger_ok == i + 1
    assert gate.entered.wait(WAIT_S)
    gate.release.set()
    final = NewRecord(type=int(RecordType.NOTE), payload=b"final")
    assert h.close(final).is_ok
    assert h.metrics().state is WriterState.CLOSED
    assert h.durable_seq == h.enqueued_seq == 41
    assert _payloads(tmp_path) == [bytes([i]) * 16 for i in range(40)] + [b"final"]
    assert isinstance(h.submit(_rec(99)).danger_err, Closed)
    assert h.close().is_ok  # idempotent


# frob:ticket 01M6W7R2DCY0H5XQ9F53F2W55E
# frob:tests python/sadi/store/writer_thread.py::WriterHandle.durable_seq
def test_durable_seq_monotonic_under_concurrent_producers(tmp_path: Path) -> None:
    """Concurrent producers get unique dense seqs; observed durable_seq never decreases."""
    h = _open(tmp_path, batch_max_records=8)
    per_thread = 50
    threads = 4
    got: list[list[int]] = [[] for _ in range(threads)]
    observed: list[list[int]] = [[] for _ in range(threads)]

    def produce(t: int) -> None:
        """Submit records and sample durable_seq after each."""
        for i in range(per_thread):
            got[t].append(
                h.submit(NewRecord(type=int(RecordType.NOTE), payload=bytes([t, i]))).danger_ok
            )
            observed[t].append(h.durable_seq)

    workers = [threading.Thread(target=produce, args=(t,)) for t in range(threads)]
    for w in workers:
        w.start()
    for w in workers:
        w.join()
    assert sorted(s for g in got for s in g) == list(range(1, threads * per_thread + 1))
    for samples in observed:
        assert samples == sorted(samples)
    assert h.close().is_ok
    disk = _payloads(tmp_path)
    assert len(disk) == threads * per_thread
    for t in range(threads):  # per-producer order preserved on disk
        mine = [p[1] for p in disk if p[0] == t]
        assert mine == list(range(per_thread))


# frob:ticket 01M6W7R2DCY0H5XQ9F53F2W55E
# frob:tests python/sadi/store/writer_thread.py::WriterHandle.submit
def test_invalid_record_is_typed_error(tmp_path: Path) -> None:
    """A record the WAL refuses is InvalidRecord, not an exception."""
    h = _open(tmp_path)
    res = h.submit(NewRecord(type=0, payload=b"x"))
    assert isinstance(res.danger_err, InvalidRecord)
    assert h.close().is_ok


# frob:ticket 01M6W7R2DCY0H5XQ9F53F2W55E
# frob:tests python/sadi/store/writer_thread.py::map_wal_error
@pytest.mark.parametrize(
    ("wal_err", "expected"),
    [
        (WalTimeout(what="queue space", waited_s=2.0), Backpressure),
        (WalTimeout(what="durable seq 3", waited_s=2.0), Stalled),
        (WalClosed(), Closed),
        (WalInvalidRecord(reason="r"), InvalidRecord),
        (WalInternal(detail="d"), Internal),
        (WalFailed(reason="r", errno=errno.ENOSPC), DiskFull),
        (WalFailed(reason="r", errno=errno.EIO), IoError),
        (WalFailed(reason="r"), IoError),
        (WalDurable(error=DurableIo(errno=errno.ENOSPC)), DiskFull),
        (WalDurable(error=DurableIo(errno=errno.EIO)), IoError),
    ],
)
def test_map_wal_error(wal_err: object, expected: type[WriterError]) -> None:
    """Every WAL error maps to its documented writer error."""
    assert isinstance(map_wal_error(wal_err), expected)  # type: ignore[arg-type]


# frob:ticket 01M6W7R2DCY0H5XQ9F53F2W55E
# frob:tests python/sadi/store/writer_thread.py::_Ring.summary
def test_ring_summary_nearest_rank_and_eviction() -> None:
    """Percentiles use nearest rank; the ring keeps only the newest samples."""
    ring = _Ring(100)
    assert ring.summary().count == 0
    for v in range(1, 201):
        ring.add(float(v))
    s = ring.summary()
    assert s.count == 100
    assert s.last_ms == 200.0
    assert s.p50_ms == 150.0
    assert s.p99_ms == 199.0
