"""Acquisition pipeline: raw block -> WAL (durable) -> analysis -> display, in that order only.

Implements the display gate of docs/data-safety.md section 6.4 (invariant I6). The acquisition
thread calls `AcquisitionPipeline.ingest`, which only enqueues the block on the WAL writer thread
(DS8) and parks it in a pending queue; it never waits for fsync. A separate forwarder thread
releases a parked item to the settle detector and the internal `Bus` once `durable_seq` covers its
seq. Analysis and display can fail, lag or drop events without touching raw data: the bus drops the
oldest event of a slow subscriber, never a raw sample. A WAL failure, stall or backpressure halts
acquisition loudly. Human-facing description: docs/core/pipeline.md.
"""

# frob:ticket 01M6W7R36G6BYYB4RBC60ZNFTD
from __future__ import annotations

import math
import threading
import time
from collections import deque
from collections.abc import Callable
from typing import Any, Protocol

import numpy as np
from pydantic import BaseModel, ConfigDict, Field
from typani import Err, ErrorSet, Ok, Result

from sadi.core.events import PointV1
from sadi.labs.lctt.settle_stream import (
    PointRecord,
    StreamConfig,
    StreamingSettleDetector,
    StreamStatus,
)
from sadi.logging_setup import get_logger
from sadi.store.events import point_record
from sadi.store.records import (
    MarkerV1,
    NewRecord,
    RecordType,
    encode_raw_block,
    encode_raw_junk,
    json_record,
)
from sadi.store.writer_thread import WriterError, WriterMetrics

_log = get_logger(__name__)

Seq = int

#: RAW_JUNK reason code 1: resync discarded bytes (docs/data-safety.md section 3.5).
JUNK_REASON_RESYNC = 1

#: Default decimated points per trace frame sent to the display.
DEFAULT_MAX_FRAME_POINTS = 256
#: Default bounded depth of each bus subscription, in events.
DEFAULT_SUBSCRIBER_DEPTH = 1024
_FORWARD_POLL_S = 0.2


class PipelineError(ErrorSet):
    """Pipeline refusals that are not WAL errors; the description says what to do."""

    Halted = "Acquisition was stopped because saving failed; fix the disk and resume"
    BadBlock = "The block does not match the pipeline configuration (packet length or shape)"


# ---- seams -------------------------------------------------------------------------------


class BlockLike(Protocol):
    """The slice of `sadi_py.Block` the pipeline reads (lets tests use plain objects)."""

    raw: bytes
    volts: Any
    n_samples: int
    msg_count: Any
    dropped_bytes: int


class WalSink(Protocol):
    """The slice of `WriterHandle` the pipeline needs; the real handle satisfies it."""

    def submit(self, record: NewRecord) -> Result[Seq, WriterError]:
        """Enqueue a record and return its seq without waiting for fsync."""
        ...

    def wait_durable(self, seq: Seq, timeout_s: float | None) -> Result[None, WriterError]:
        """Block until `seq` is durable, the writer fails, or the timeout elapses."""
        ...

    @property
    def durable_seq(self) -> Seq:
        """Highest durable seq."""
        ...

    @property
    def enqueued_seq(self) -> Seq:
        """Highest assigned seq."""
        ...

    def on_failure(self, listener: Callable[[WriterError], None]) -> None:
        """Register a one-shot callback run when the writer fails."""
        ...

    def check_health(self) -> Result[None, WriterError]:
        """Return the failure or stall, if any."""
        ...

    def metrics(self) -> WriterMetrics:
        """Return the writer metrics snapshot."""
        ...


# ---- config and bus events ---------------------------------------------------------------


class PipelineConfig(BaseModel):
    """Frozen pipeline parameters: packet geometry, rate, display channels and decimation."""

    model_config = ConfigDict(frozen=True)

    stream: StreamConfig
    sample_rate_hz: float = Field(gt=0)
    packet_len: int = Field(default=612, gt=0)
    lvdt_channel: int = Field(default=0, ge=0, le=3)
    trace_channels: tuple[int, ...] = (0, 1, 2, 3)
    max_frame_points: int = Field(default=DEFAULT_MAX_FRAME_POINTS, gt=0)


class TraceFrame(BaseModel):
    """A decimated, durable block for the display; carries the durability watermarks."""

    model_config = ConfigDict(frozen=True)

    raw_seq: Seq
    t0_s: float
    dt_s: float
    channels: dict[int, list[float]]
    durable_seq: Seq
    enqueued_seq: Seq


class SettleUpdate(BaseModel):
    """Settle state of the open point after a durable block was analysed."""

    model_config = ConfigDict(frozen=True)

    raw_seq: Seq
    status: StreamStatus


class ResultUpdate(BaseModel):
    """A finalized per-point result (closed, settled or forced early)."""

    model_config = ConfigDict(frozen=True)

    raw_seq: Seq
    record: PointRecord


class AnalysisFailed(BaseModel):
    """Analysis rejected or crashed on a block; raw data is unaffected and was saved."""

    model_config = ConfigDict(frozen=True)

    raw_seq: Seq
    reason: str


class PipelineStopped(BaseModel):
    """Acquisition was halted; `reason` is the marker reason and `hint` is for the UI."""

    model_config = ConfigDict(frozen=True)

    reason: str
    hint: str
    last_durable_seq: Seq


BusEvent = TraceFrame | SettleUpdate | ResultUpdate | AnalysisFailed | PipelineStopped


class Subscription:
    """Bounded drop-oldest event queue for one bus consumer; a slow consumer only loses events."""

    def __init__(self, name: str, depth: int) -> None:
        """Create an empty subscription holding at most `depth` events."""
        self.name = name
        self._events: deque[BusEvent] = deque(maxlen=depth)
        self._lock = threading.Lock()
        self._dropped = 0

    def _offer(self, event: BusEvent) -> None:
        """Append `event`, evicting (and counting) the oldest when full; never blocks."""
        with self._lock:
            if self._events.maxlen is not None and len(self._events) == self._events.maxlen:
                self._dropped += 1
                if self._dropped == 1 or self._dropped % 1000 == 0:
                    _log.warning("subscriber %s slow: %d events dropped", self.name, self._dropped)
            self._events.append(event)

    @property
    def dropped(self) -> int:
        """Number of derived events this consumer lost (raw data is never affected)."""
        with self._lock:
            return self._dropped

    def drain(self) -> list[BusEvent]:
        """Remove and return all queued events, oldest first."""
        with self._lock:
            out = list(self._events)
            self._events.clear()
        return out


class Bus:
    """Internal publish/subscribe bus; publishing never blocks and never raises."""

    def __init__(self) -> None:
        """Create a bus with no subscribers."""
        self._lock = threading.Lock()
        self._subs: list[Subscription] = []

    def subscribe(self, name: str, depth: int = DEFAULT_SUBSCRIBER_DEPTH) -> Subscription:
        """Add and return a bounded subscription named `name`."""
        sub = Subscription(name, depth)
        with self._lock:
            self._subs.append(sub)
        _log.info("bus subscriber %s added (depth %d)", name, depth)
        return sub

    def publish(self, event: BusEvent) -> None:
        """Offer `event` to every subscriber."""
        with self._lock:
            subs = list(self._subs)
        for sub in subs:
            sub._offer(event)  # noqa: SLF001 - Bus and Subscription are one unit


# ---- pending items -----------------------------------------------------------------------


class _Item:
    """One WAL-enqueued item awaiting durability; subclasses say what to do once durable."""

    def __init__(self, seq: Seq) -> None:
        """Remember the WAL seq that gates this item."""
        self.seq = seq


class _BlockItem(_Item):
    """A raw block with its stream-time start."""

    def __init__(self, seq: Seq, volts: Any, t0_s: float) -> None:
        """Keep the volts (n, 4) and the time of its first sample."""
        super().__init__(seq)
        self.volts = volts
        self.t0_s = t0_s


class _ControlItem(_Item):
    """An ordered detector command (`load`, `close` or `force`) at stream time `t_s`."""

    def __init__(self, seq: Seq, action: str, t_s: float) -> None:
        """Keep the command name and its stream time."""
        super().__init__(seq)
        self.action = action
        self.t_s = t_s


# ---- pipeline ----------------------------------------------------------------------------


class AcquisitionPipeline:
    """Raw -> WAL -> (durable gate) -> settle analysis -> bus; see the module docstring."""

    def __init__(
        self,
        wal: WalSink,
        config: PipelineConfig,
        bus: Bus | None = None,
        *,
        stop_device: Callable[[], None] | None = None,
        clock_ns: Callable[[], int] = time.monotonic_ns,
    ) -> None:
        """Wire the pipeline to a WAL sink; `stop_device` is called once on a loud halt."""
        self._wal = wal
        self._cfg = config
        self.bus = bus if bus is not None else Bus()
        self._stop_device = stop_device
        self._clock_ns = clock_ns
        self._detector = StreamingSettleDetector(config.stream)
        self._pending: deque[_Item] = deque()
        self._producer_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._ingested_samples = 0
        self._last_raw_seq: Seq = 0
        self._halted_reason: str | None = None
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        wal.on_failure(self._on_wal_failure)

    # -- producer side (acquisition thread) ------------------------------------------------

    @property
    def halted(self) -> bool:
        """True once acquisition was stopped; ingest then refuses new blocks."""
        with self._state_lock:
            return self._halted_reason is not None

    def pending_count(self) -> int:
        """Items enqueued in the WAL but not yet released to analysis and display."""
        return len(self._pending)

    def ingest(self, block: BlockLike) -> Result[Seq, WriterError | PipelineError]:
        """Append the raw block to the WAL and park it; returns its seq without waiting on fsync.

        A WAL refusal (backpressure, closed, disk error) halts acquisition loudly and is returned.
        """
        if self.halted:
            return Err(PipelineError.Halted)
        n = int(block.n_samples)
        plen = self._cfg.packet_len
        # frob:ticket 01M6WJT02NYTS67SGG3W7KAMYM
        dropped = int(block.dropped_bytes)
        # With dropped bytes the raw length is not packet aligned, so alignment is not checked.
        misaligned = len(block.raw) % plen and not dropped
        if n <= 0 or not block.raw or misaligned or block.volts.shape[0] != n:
            _log.error("bad block: n_samples=%d raw_len=%d", n, len(block.raw))
            return Err(PipelineError.BadBlock)
        count = len(block.raw) // plen
        mono = self._clock_ns()
        if dropped:
            # Junk positions are unknown, so every received byte is kept verbatim as RAW_JUNK.
            _log.warning(
                "block dropped %d bytes; storing %d raw bytes as RAW_JUNK", dropped, len(block.raw)
            )
            record = NewRecord(
                type=int(RecordType.RAW_JUNK),
                payload=encode_raw_junk(mono, JUNK_REASON_RESYNC, bytes(block.raw)),
            )
        else:
            first_msg = int(block.msg_count[0]) if len(block.msg_count) else 0
            payload = encode_raw_block(
                bytes(block.raw), self._cfg.packet_len, mono, time.time_ns(), first_msg
            )
            record = NewRecord(type=int(RecordType.RAW_BLOCK), payload=payload)
        with self._producer_lock:
            res = self._wal.submit(record)
            if res.is_err:
                err = res.danger_err
                _log.error("raw block refused by WAL: %s", err)
                self._halt("store_" + type(err).__name__.lower(), err.hint)
                return Err(err)
            seq = res.danger_ok
            t0 = self._ingested_samples / self._cfg.sample_rate_hz
            self._ingested_samples += n
            self._last_raw_seq = seq
            self._pending.append(_BlockItem(seq, np.array(block.volts, copy=True), t0))
        _log.debug("raw block seq=%d packets=%d queued, pending=%d", seq, count, len(self._pending))
        self._wake.set()
        return Ok(seq)

    def record_point(self, point: PointV1) -> Result[Seq, WriterError | PipelineError]:
        """Append a captured POINT event to the WAL (append-only; refused once halted)."""
        if self.halted:
            return Err(PipelineError.Halted)
        with self._producer_lock:
            res = self._wal.submit(point_record(point))
        if res.is_err:
            err = res.danger_err
            _log.error("point %s refused by WAL: %s", point.point_id, err)
            self._halt("store_" + type(err).__name__.lower(), err.hint)
            return Err(err)
        _log.info("point %s phase=%s seq=%d", point.point_id, point.phase, res.danger_ok)
        return Ok(res.danger_ok)

    def mark_load_change(self) -> Result[Seq, WriterError | PipelineError]:
        """Write a load-applied marker and open a new point at the current stream time."""
        return self._control("load", "load_applied")

    def close_point(self) -> Result[Seq, WriterError | PipelineError]:
        """Write a marker and finalize the open point as it stands."""
        return self._control("close", "point_closed")

    def force_early(self) -> Result[Seq, WriterError | PipelineError]:
        """Write a marker and finalize the open point as forced early."""
        return self._control("force", "settle_forced_early")

    def _control(self, action: str, kind: str) -> Result[Seq, WriterError | PipelineError]:
        """Enqueue a MARKER and park the matching ordered detector command."""
        if self.halted:
            return Err(PipelineError.Halted)
        with self._producer_lock:
            marker = MarkerV1(kind=kind, raw_seq=self._last_raw_seq or None)
            res = self._wal.submit(json_record(RecordType.MARKER, marker))
            if res.is_err:
                err = res.danger_err
                _log.error("marker %s refused by WAL: %s", kind, err)
                self._halt("store_" + type(err).__name__.lower(), err.hint)
                return Err(err)
            seq = res.danger_ok
            t = self._ingested_samples / self._cfg.sample_rate_hz
            self._pending.append(_ControlItem(seq, action, t))
        _log.info("marker %s seq=%d at t=%.6g s", kind, seq, t)
        self._wake.set()
        return Ok(seq)

    def tick(self) -> Result[None, WriterError]:
        """Health check to call periodically; a failed or stalled writer halts acquisition."""
        res = self._wal.check_health()
        if res.is_err:
            err = res.danger_err
            self._halt("store_" + type(err).__name__.lower(), err.hint)
        return res

    # -- halt ------------------------------------------------------------------------------

    def _on_wal_failure(self, err: WriterError) -> None:
        """Writer-thread callback: the WAL failed; stop acquisition."""
        self._halt("store_" + type(err).__name__.lower(), err.hint)

    # frob:ticket 01M6WMVRTG5YQDSZYQQG368G2E
    def halt(self, reason: str, hint: str) -> None:
        """Stop acquisition once, loudly, for an external caller such as a device fault."""
        self._halt(reason, hint)

    def _halt(self, reason: str, hint: str) -> None:
        """Stop acquisition once: stop the device, best-effort stop marker, tell the display."""
        with self._state_lock:
            if self._halted_reason is not None:
                return
            self._halted_reason = reason
        _log.error("acquisition HALTED: %s (%s)", reason, hint)
        if self._stop_device is not None:
            try:
                self._stop_device()
            except Exception:  # noqa: BLE001 - halting must finish even if the device call fails
                _log.exception("stop_device raised during halt")
        marker = MarkerV1(
            kind="acquisition_stopped", raw_seq=self._last_raw_seq or None, data={"reason": reason}
        )
        stop_res = self._wal.submit(json_record(RecordType.MARKER, marker))
        if stop_res.is_err:
            _log.error("stop marker not written: %s", stop_res.danger_err)
        self.bus.publish(
            PipelineStopped(reason=reason, hint=hint, last_durable_seq=self._wal.durable_seq)
        )

    # -- durable gate (forwarder side) -----------------------------------------------------

    def pump(self) -> int:
        """Release every parked item whose seq is covered by durable_seq; return how many."""
        durable = self._wal.durable_seq
        released = 0
        while self._pending and self._pending[0].seq <= durable:
            item = self._pending.popleft()
            self._release(item, durable)
            released += 1
        return released

    def _release(self, item: _Item, durable: Seq) -> None:
        """Run analysis and publish for one durable item; failures stay inside the pipeline."""
        try:
            if isinstance(item, _BlockItem):
                self._release_block(item, durable)
            elif isinstance(item, _ControlItem):
                self._release_control(item)
        except Exception as exc:  # noqa: BLE001 - analysis bugs must never touch raw data
            _log.exception("analysis crashed on seq %d", item.seq)
            self.bus.publish(AnalysisFailed(raw_seq=item.seq, reason=repr(exc)))

    def _release_block(self, item: _BlockItem, durable: Seq) -> None:
        """Publish a decimated trace frame, then feed the LVDT column to the settle detector."""
        cfg = self._cfg
        volts = item.volts
        n = volts.shape[0]
        stride = max(1, math.ceil(n / cfg.max_frame_points))
        self.bus.publish(
            TraceFrame(
                raw_seq=item.seq,
                t0_s=item.t0_s,
                dt_s=stride / cfg.sample_rate_hz,
                channels={c: volts[::stride, c].tolist() for c in cfg.trace_channels},
                durable_seq=durable,
                enqueued_seq=self._wal.enqueued_seq,
            )
        )
        times = (item.t0_s + np.arange(n) / cfg.sample_rate_hz).tolist()
        res = self._detector.push(times, volts[:, cfg.lvdt_channel].tolist())
        if res.is_err:
            _log.warning("settle analysis rejected seq %d: %s", item.seq, res.danger_err)
            self.bus.publish(AnalysisFailed(raw_seq=item.seq, reason=str(res.danger_err)))
            return
        self.bus.publish(SettleUpdate(raw_seq=item.seq, status=res.danger_ok))

    def _release_control(self, item: _ControlItem) -> None:
        """Apply an ordered detector command and publish its outcome."""
        if item.action == "load":
            res: Result[Any, Any] = self._detector.mark_load_change(item.t_s)
        elif item.action == "close":
            res = self._detector.close_point()
        else:
            res = self._detector.force_early()
        if res.is_err:
            _log.warning("control %s rejected: %s", item.action, res.danger_err)
            self.bus.publish(AnalysisFailed(raw_seq=item.seq, reason=str(res.danger_err)))
        elif isinstance(res.danger_ok, PointRecord):
            self.bus.publish(ResultUpdate(raw_seq=item.seq, record=res.danger_ok))

    # -- forwarder thread ------------------------------------------------------------------

    def start(self) -> None:
        """Start the forwarder thread that releases durable items (idempotent)."""
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._forward_loop, name="sadi-forwarder")
        self._thread.start()
        _log.info("pipeline forwarder started")

    def stop(self, drain_timeout_s: float = 10.0) -> None:
        """Release what becomes durable within the timeout, then join the forwarder."""
        deadline = time.monotonic() + drain_timeout_s
        while self._pending and time.monotonic() < deadline and not self.halted:
            self._wake.set()
            time.sleep(0.01)
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join()
            self._thread = None
        self.pump()
        _log.info("pipeline stopped; %d items never released", len(self._pending))

    def _forward_loop(self) -> None:
        """Release items as they become durable; never runs on the acquisition path."""
        while not self._stop.is_set():
            self.pump()
            head = self._pending[0].seq if self._pending else None
            if head is None:
                self._wake.wait(_FORWARD_POLL_S)
                self._wake.clear()
                continue
            res = self._wal.wait_durable(head, _FORWARD_POLL_S)
            if res.is_err:
                # Failure or slow disk: items stay parked (undisplayed); poll again.
                self._stop.wait(0.05)
