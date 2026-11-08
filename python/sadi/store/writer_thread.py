"""Thread-safe facade over the WAL writer thread: typed errors, backpressure, metrics, stall watch.

Follows docs/data-safety.md section 7 (DS8). The `WalWriter` thread owns the segment fd and does
every write and fsync; producers only enqueue through `WriterHandle.submit`, so fsync latency
never runs on the acquisition path. The queue is bounded and a full queue is reported as
`Backpressure`; a record is never dropped, coalesced or reordered.
"""

# frob:ticket 01M6W7R2DCY0H5XQ9F53F2W55E
from __future__ import annotations

import errno
import shutil
import threading
import time
import uuid
from collections import deque
from collections.abc import Callable
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict
from typani import Err, Ok, Result

from sadi.logging_setup import get_logger
from sadi.store.durable import DurableIo
from sadi.store.records import NewRecord
from sadi.store.wal import (
    WalClosed,
    WalConfig,
    WalDurable,
    WalError,
    WalFailed,
    WalInternal,
    WalInvalidRecord,
    WalStats,
    WalTimeout,
    WalWriter,
)

_log = get_logger(__name__)

Seq = int

RING_SIZE = 256
STALL_TIMEOUT_S = 5.0
_QUEUE_SPACE = "queue space"

# ---- errors ------------------------------------------------------------------------------


class WriterError(BaseModel):
    """Base of all writer-facade failures; `hint` is shown in the UI."""

    model_config = ConfigDict(frozen=True)
    hint: str = ""


class Backpressure(WriterError):
    """The bounded queue stayed full for `waited_s`; nothing was enqueued, nothing was lost."""

    waited_s: float
    queue_depth_items: int
    queue_depth_bytes: int
    hint: str = "The data disk is slow; acquisition must pause. Data already shown is safe."


class Closed(WriterError):
    """The writer is draining or closed and accepts no new records."""

    hint: str = "The recording is closed."


class DiskFull(WriterError):
    """The disk is full (ENOSPC); undurable records are kept in memory."""

    reason: str
    hint: str = "The data disk is full. Data already shown is safe; free space, then retry."


class IoError(WriterError):
    """A write, fsync or file operation failed; undurable records are kept in memory."""

    reason: str
    errno: int | None = None
    hint: str = "Saving failed. Data already shown is safe; check the disk, then retry."


class Stalled(WriterError):
    """Durability made no progress for `waited_s` while records were queued."""

    waited_s: float
    durable_seq: int
    enqueued_seq: int
    hint: str = (
        "The data disk is not responding. Data already shown is safe; new data is held in "
        "memory. Free space or change disk, then resume."
    )


class InvalidRecord(WriterError):
    """The caller supplied a record the WAL refuses to write (a bug upstream)."""

    reason: str


class Internal(WriterError):
    """An unexpected exception in the writer thread (a bug)."""

    detail: str
    hint: str = "An internal error stopped saving; see the log."


def map_wal_error(err: WalError) -> WriterError:
    """Translate a `WalError` into the typed writer error the pipeline and UI act on."""
    if isinstance(err, WalTimeout):
        if err.what == _QUEUE_SPACE:
            return Backpressure(waited_s=err.waited_s, queue_depth_items=0, queue_depth_bytes=0)
        return Stalled(waited_s=err.waited_s, durable_seq=0, enqueued_seq=0)
    if isinstance(err, WalClosed):
        return Closed()
    if isinstance(err, WalInvalidRecord):
        return InvalidRecord(reason=err.reason)
    if isinstance(err, WalInternal):
        return Internal(detail=err.detail)
    if isinstance(err, WalFailed):
        if err.errno == errno.ENOSPC:
            return DiskFull(reason=err.reason)
        return IoError(reason=err.reason, errno=err.errno)
    if isinstance(err, WalDurable):
        inner = err.error
        if isinstance(inner, DurableIo):
            if inner.errno == errno.ENOSPC:
                return DiskFull(reason=repr(inner))
            return IoError(reason=repr(inner), errno=inner.errno)
        return IoError(reason=repr(inner))
    return IoError(reason=repr(err))


# ---- metrics -----------------------------------------------------------------------------


class WriterState(StrEnum):
    """Writer state as reported in metrics (ROTATING is not distinguished from RUNNING)."""

    RUNNING = "RUNNING"
    STALLED = "STALLED"
    FAILED = "FAILED"
    DRAINING = "DRAINING"
    CLOSED = "CLOSED"


class LatencySummary(BaseModel):
    """Last, p50 and p99 (nearest rank) of a millisecond ring; all zero when empty."""

    model_config = ConfigDict(frozen=True)
    count: int = 0
    last_ms: float = 0.0
    p50_ms: float = 0.0
    p99_ms: float = 0.0


class WriterMetrics(BaseModel):
    """Snapshot of writer health read by the status bar and the pipeline (section 7.2)."""

    model_config = ConfigDict(frozen=True)
    state: WriterState
    queue_depth_items: int
    queue_depth_bytes: int
    enqueued_seq: int
    durable_seq: int
    last_batch_records: int
    batches: int
    fsync_latency: LatencySummary
    submit_wait: LatencySummary
    backpressure_events: int
    segment_no: int
    segment_bytes: int
    free_bytes: int | None
    error: WriterError | None


class _Ring:
    """Fixed-size sample ring; callers serialise access."""

    def __init__(self, size: int) -> None:
        """Create an empty ring holding at most `size` samples."""
        self._samples: deque[float] = deque(maxlen=size)

    def add(self, value: float) -> None:
        """Record one sample, evicting the oldest when full."""
        self._samples.append(value)

    def summary(self) -> LatencySummary:
        """Return last, p50 and p99 of the current samples."""
        if not self._samples:
            return LatencySummary()
        ordered = sorted(self._samples)
        n = len(ordered)

        def rank(p: float) -> float:
            """Nearest-rank percentile."""
            return ordered[max(0, min(n - 1, -(-int(p * n) // 100) - 1))]

        return LatencySummary(count=n, last_ms=self._samples[-1], p50_ms=rank(50), p99_ms=rank(99))


# ---- handle ------------------------------------------------------------------------------


class WriterHandle:
    """Thread-safe producer facade; `_lock` is a leaf lock (nothing is acquired while held)."""

    def __init__(
        self,
        wal: WalWriter,
        *,
        stall_timeout_s: float = STALL_TIMEOUT_S,
        clock: Callable[[], float] = time.monotonic,
        free_bytes_fn: Callable[[], int | None] | None = None,
    ) -> None:
        """Wrap an open `WalWriter`; use `WriterHandle.open` to create both."""
        self._wal = wal
        self._stall_timeout_s = stall_timeout_s
        self._clock = clock
        self._free_bytes_fn = free_bytes_fn or (lambda: None)
        self._lock = threading.Lock()
        self._fsync_ring = _Ring(RING_SIZE)
        self._wait_ring = _Ring(RING_SIZE)
        self._backpressure_events = 0
        self._published_durable = 0
        self._progress_seq = 0
        self._progress_at = clock()
        self._stalled: Stalled | None = None
        self._failure: WriterError | None = None
        self._failure_listeners: list[Callable[[WriterError], None]] = []
        wal.set_fsync_observer(self._on_fsync)
        wal.set_failure_observer(self._on_failure)

    @staticmethod
    def open(
        wal_dir: Path,
        session_uuid: uuid.UUID,
        first_seq: int = 1,
        config: WalConfig | None = None,
        *,
        stall_timeout_s: float = STALL_TIMEOUT_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> Result[WriterHandle, WriterError]:
        """Open the WAL (starting its writer thread) and return the handle."""
        opened = WalWriter.open(wal_dir, session_uuid, first_seq, config)
        if opened.is_err:
            err = map_wal_error(opened.danger_err)
            _log.error("writer open failed: %s", err)
            return Err(err)
        handle = WriterHandle(
            opened.danger_ok,
            stall_timeout_s=stall_timeout_s,
            clock=clock,
            free_bytes_fn=lambda: _free_bytes(wal_dir),
        )
        _log.info("writer handle ready at %s", wal_dir)
        return Ok(handle)

    # -- producer side ---------------------------------------------------------------------

    def submit(self, record: NewRecord) -> Result[Seq, WriterError]:
        """Enqueue `record` and return its seq; blocks up to the submit timeout when full.

        On a full queue the result is `Err(Backpressure)` and the record was NOT enqueued
        (the caller still holds it and must retry or stop acquisition); it is never dropped here.
        """
        start = self._clock()
        res = self._wal.append_nowait(record)
        waited_ms = (self._clock() - start) * 1000.0
        with self._lock:
            self._wait_ring.add(waited_ms)
        if res.is_ok:
            return Ok(res.danger_ok)
        err = map_wal_error(res.danger_err)
        if isinstance(err, Backpressure):
            stats = self._wal.stats()
            err = err.model_copy(
                update={
                    "queue_depth_items": stats.queue_depth_items,
                    "queue_depth_bytes": stats.queue_depth_bytes,
                }
            )
            with self._lock:
                self._backpressure_events += 1
            _log.error(
                "backpressure: queue full (%d items, %d bytes) for %.3fs; record not enqueued",
                err.queue_depth_items,
                err.queue_depth_bytes,
                err.waited_s,
            )
        else:
            _log.error("submit refused: %s", err)
        return Err(err)

    def wait_durable(self, seq: Seq, timeout_s: float | None) -> Result[None, WriterError]:
        """Block until `durable_seq >= seq` (the display gate), the writer fails, or timeout."""
        res = self._wal.wait_durable(seq, timeout_s)
        if res.is_ok:
            return Ok(None)
        err = map_wal_error(res.danger_err)
        if isinstance(err, Stalled):
            stats = self._wal.stats()
            err = err.model_copy(
                update={"durable_seq": stats.durable_seq, "enqueued_seq": stats.enqueued_seq}
            )
        _log.error("wait_durable(%d) failed: %s", seq, err)
        return Err(err)

    @property
    def durable_seq(self) -> Seq:
        """Highest durable seq, published monotonically (never lower than a prior reading)."""
        seq = self._wal.durable_seq
        with self._lock:
            if seq > self._published_durable:
                self._published_durable = seq
            return self._published_durable

    @property
    def enqueued_seq(self) -> Seq:
        """Highest seq assigned so far."""
        return self._wal.enqueued_seq

    def on_failure(self, listener: Callable[[WriterError], None]) -> None:
        """Register a callback run on the writer thread once when the writer fails.

        If the writer already failed the listener runs immediately on the caller's thread.
        Listeners must not raise or block; use them to stop acquisition loudly.
        """
        with self._lock:
            failure = self._failure
            if failure is None:
                self._failure_listeners.append(listener)
        if failure is not None:
            listener(failure)

    def check_health(self) -> Result[None, WriterError]:
        """Return the typed failure if the writer FAILED, or Stalled if durability is stuck.

        Call periodically (the pipeline tick). A stall clears itself when durable_seq advances.
        """
        with self._lock:
            failure = self._failure
        if failure is not None:
            return Err(failure)
        stats = self._wal.stats()
        now = self._clock()
        with self._lock:
            if stats.durable_seq > self._progress_seq or stats.durable_seq >= stats.enqueued_seq:
                if self._stalled is not None:
                    _log.info("writer stall cleared at durable_seq %d", stats.durable_seq)
                self._progress_seq = stats.durable_seq
                self._progress_at = now
                self._stalled = None
                return Ok(None)
            waited = now - self._progress_at
            if waited < self._stall_timeout_s:
                return Ok(None)
            stalled = Stalled(
                waited_s=waited, durable_seq=stats.durable_seq, enqueued_seq=stats.enqueued_seq
            )
            first = self._stalled is None
            self._stalled = stalled
        if first:
            _log.error("writer STALLED: %s", stalled)
        return Err(stalled)

    def metrics(self) -> WriterMetrics:
        """Return a consistent snapshot of queue, durability, latency and error state."""
        stats = self._wal.stats()
        free = self._free_bytes_fn()
        with self._lock:
            return self._metrics_locked(stats, free)

    def undurable_count(self) -> int:
        """Return how many records are held in memory and not known durable (after FAILED)."""
        return len(self._wal.undurable_records())

    def close(self, final: NewRecord | None = None) -> Result[None, WriterError]:
        """Optionally enqueue `final` (e.g. SESSION_CLOSE), drain the queue, fsync and join."""
        final_err: WriterError | None = None
        if final is not None:
            queued = self.submit(final)
            if queued.is_err:
                final_err = queued.danger_err
                _log.error("closing without final record: %s", final_err)
        closed = self._wal.close()
        if closed.is_err:
            err = map_wal_error(closed.danger_err)
            _log.error("writer closed with error: %s", err)
            return Err(err)
        if final_err is not None:
            return Err(final_err)
        _log.info("writer closed; durable_seq=%d", self._wal.durable_seq)
        return Ok(None)

    # -- internals -------------------------------------------------------------------------

    def _metrics_locked(self, stats: WalStats, free: int | None) -> WriterMetrics:
        """Build the snapshot; `_lock` is held."""
        state = WriterState(stats.state)
        if state is WriterState.RUNNING and self._stalled is not None:
            state = WriterState.STALLED
        self._published_durable = max(self._published_durable, stats.durable_seq)
        return WriterMetrics(
            state=state,
            queue_depth_items=stats.queue_depth_items,
            queue_depth_bytes=stats.queue_depth_bytes,
            enqueued_seq=stats.enqueued_seq,
            durable_seq=self._published_durable,
            last_batch_records=stats.last_batch_records,
            batches=stats.batches,
            fsync_latency=self._fsync_ring.summary(),
            submit_wait=self._wait_ring.summary(),
            backpressure_events=self._backpressure_events,
            segment_no=stats.segment_no,
            segment_bytes=stats.segment_bytes,
            free_bytes=free,
            error=self._failure or self._stalled,
        )

    def _on_fsync(self, ms: float) -> None:
        """Writer-thread hook: record one fsync latency sample."""
        with self._lock:
            self._fsync_ring.add(ms)

    def _on_failure(self, error: WalError) -> None:
        """Writer-thread hook: remember the typed failure and notify listeners once."""
        mapped = map_wal_error(error)
        with self._lock:
            self._failure = mapped
            listeners = list(self._failure_listeners)
            self._failure_listeners.clear()
        _log.error("writer FAILED: %s (undurable=%d)", mapped, self.undurable_count())
        for listener in listeners:
            try:
                listener(mapped)
            except Exception:  # noqa: BLE001 - one bad listener must not hide the failure
                _log.exception("writer failure listener raised")


def _free_bytes(path: Path) -> int | None:
    """Return free bytes on the filesystem holding `path`, or None if it cannot be read."""
    try:
        return shutil.disk_usage(path).free
    except OSError as exc:
        _log.warning("free space unreadable at %s: %s", path, exc)
        return None
