"""Tests for the acquisition pipeline: durable-before-display, fault injection, bus, halt."""

from __future__ import annotations

import errno
import logging
import threading
import time
import uuid
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from typani import Err

from sadi.core.pipeline import (
    AcquisitionPipeline,
    AnalysisFailed,
    Bus,
    PipelineConfig,
    PipelineError,
    PipelineStopped,
    ResultUpdate,
    SettleUpdate,
    TraceFrame,
)
from sadi.labs.lctt.settle import SettleConfig
from sadi.labs.lctt.settle_stream import SettleState, StreamConfig
from sadi.store import durable, failpoints
from sadi.store.records import RecordType, decode_raw_junk
from sadi.store.wal import WalClosed, WalConfig, WalReader
from sadi.store.writer_thread import Backpressure, Stalled, WriterError, WriterHandle

SESSION = uuid.UUID(int=0x60FD)
WAIT_S = 10.0
RATE = 1000.0
PACKET = 8
N = 100


@pytest.fixture(autouse=True)
def _reset() -> Iterator[None]:
    """Clear failpoints around each test."""
    failpoints.clear()
    yield
    failpoints.clear()


class _Block:
    """Plain stand-in for `sadi_py.Block` (the pipeline reads only these attributes)."""

    def __init__(self, level: float = 1.0, n: int = N, *, nan: bool = False) -> None:
        """Build n samples at constant `level` volts; `nan` poisons the LVDT column."""
        self.volts = np.full((n, 4), level)
        if nan:
            self.volts[0, 0] = float("nan")
        self.n_samples = n
        self.raw = bytes(range(256))[:PACKET] * n
        self.msg_count = np.arange(n, dtype=np.uint32)
        self.dropped_bytes = 0


class _Clock:
    """Manually advanced monotonic clock so stall tests need no sleeping."""

    def __init__(self) -> None:
        """Start at t=0."""
        self.now = 0.0

    def __call__(self) -> float:
        """Return the current fake time."""
        return self.now


class _Gate:
    """Replaces fsync_file: blocks every call until released."""

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


def _config() -> PipelineConfig:
    """Pipeline config with a quick settle detector and small packets."""
    settle = SettleConfig(window_s=0.05, threshold=1.0, min_dwell_s=0.05, min_points=5)
    return PipelineConfig(
        stream=StreamConfig(settle=settle), sample_rate_hz=RATE, packet_len=PACKET
    )


def _open(tmp_path: Path, **kw: Any) -> WriterHandle:
    """Open a real WAL writer handle under tmp_path."""
    wal = tmp_path / "wal"
    wal.mkdir(exist_ok=True)
    handle_kw = {k: v for k, v in kw.items() if k in ("stall_timeout_s", "clock")}
    cfg = {k: v for k, v in kw.items() if k not in handle_kw}
    res = WriterHandle.open(wal, SESSION, 1, WalConfig(**cfg), **handle_kw)
    assert res.is_ok, res
    return res.danger_ok


def _wal_raw_seqs(tmp_path: Path) -> set[int]:
    """Seqs of all RAW_BLOCK records that verify on disk."""
    return {
        r.danger_ok.seq
        for r in WalReader(tmp_path / "wal").records()
        if r.is_ok and r.danger_ok.type == int(RecordType.RAW_BLOCK)
    }


def _frames(events: Sequence[object]) -> list[TraceFrame]:
    """Filter trace frames out of drained bus events."""
    return [e for e in events if isinstance(e, TraceFrame)]


# frob:ticket 01M6W7R36G6BYYB4RBC60ZNFTD
# frob:tests python/sadi/core/pipeline.py::WalSink.submit
# frob:tests python/sadi/core/pipeline.py::WalSink.wait_durable
# frob:tests python/sadi/core/pipeline.py::WalSink.durable_seq
# frob:tests python/sadi/core/pipeline.py::WalSink.enqueued_seq
# frob:tests python/sadi/core/pipeline.py::WalSink.on_failure
# frob:tests python/sadi/core/pipeline.py::WalSink.check_health
# frob:tests python/sadi/core/pipeline.py::WalSink.metrics
# frob:tests python/sadi/core/pipeline.py::Subscription.drain
# frob:tests python/sadi/core/pipeline.py::Bus.__init__
# frob:tests python/sadi/core/pipeline.py::AcquisitionPipeline.__init__
# frob:tests python/sadi/core/pipeline.py::AcquisitionPipeline.ingest
# frob:tests python/sadi/core/pipeline.py::AcquisitionPipeline.pump
def test_blocks_reach_display_in_order_after_durable(tmp_path: Path) -> None:
    """Trace frames and settle updates appear in seq order, each covered by durable_seq."""
    h = _open(tmp_path)
    pipe = AcquisitionPipeline(h, _config())
    sub = pipe.bus.subscribe("t")
    seqs = [pipe.ingest(_Block()).danger_ok for _ in range(4)]
    assert seqs == [1, 2, 3, 4]
    assert h.wait_durable(4, WAIT_S).is_ok
    assert pipe.pump() == 4
    events = sub.drain()
    frames = _frames(events)
    assert [f.raw_seq for f in frames] == seqs
    assert all(f.durable_seq >= f.raw_seq for f in frames)
    assert frames[1].t0_s == pytest.approx(N / RATE)
    assert len(frames[0].channels[0]) == 100  # under max_frame_points: undecimated
    assert sum(isinstance(e, SettleUpdate) for e in events) == 4
    assert h.close().is_ok
    assert _wal_raw_seqs(tmp_path) == set(seqs)


# frob:ticket 01M6W7R36G6BYYB4RBC60ZNFTD
# frob:tests python/sadi/core/pipeline.py::AcquisitionPipeline._release_block
def test_trace_frames_are_decimated(tmp_path: Path) -> None:
    """A block larger than max_frame_points is strided down to at most that many points."""
    h = _open(tmp_path)
    cfg = _config().model_copy(update={"max_frame_points": 10})
    pipe = AcquisitionPipeline(h, cfg)
    sub = pipe.bus.subscribe("t")
    assert pipe.ingest(_Block()).is_ok
    assert h.wait_durable(1, WAIT_S).is_ok
    pipe.pump()
    frame = _frames(sub.drain())[0]
    assert len(frame.channels[0]) == 10
    assert frame.dt_s == pytest.approx(10 / RATE)
    h.close()


# frob:ticket 01M6W7R36G6BYYB4RBC60ZNFTD
# frob:tests python/sadi/core/pipeline.py::AcquisitionPipeline.ingest
# frob:tests python/sadi/core/pipeline.py::AcquisitionPipeline.pump
def test_slow_fsync_never_blocks_ingest_and_display_waits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With fsync stuck, ingest returns at once, nothing is displayed, then all appears."""
    h = _open(tmp_path)
    gate = _Gate(durable.fsync_file)
    monkeypatch.setattr(durable, "fsync_file", gate)
    pipe = AcquisitionPipeline(h, _config())
    sub = pipe.bus.subscribe("t")
    assert pipe.ingest(_Block()).is_ok
    assert gate.entered.wait(WAIT_S)
    more = [pipe.ingest(_Block()) for _ in range(3)]  # fsync is stuck: must not wait on it
    assert all(r.is_ok for r in more)
    assert pipe.pump() == 0
    assert sub.drain() == []
    assert pipe.pending_count() == 4
    gate.release.set()
    assert h.wait_durable(4, WAIT_S).is_ok
    assert pipe.pump() == 4
    assert [f.raw_seq for f in _frames(sub.drain())] == [1, 2, 3, 4]
    h.close()


# frob:ticket 01M6WMVRTG5YQDSZYQQG368G2E
# frob:tests python/sadi/core/pipeline.py::AcquisitionPipeline.halt
def test_public_halt_stops_once_and_refuses_ingest(tmp_path: Path) -> None:
    """Public halt() stops the device, publishes one PipelineStopped, and is idempotent."""
    h = _open(tmp_path)
    calls: list[int] = []
    pipe = AcquisitionPipeline(h, _config(), stop_device=lambda: calls.append(1))
    sub = pipe.bus.subscribe("t")
    pipe.halt("device_fault", "check cable")
    pipe.halt("device_fault", "again")
    assert pipe.halted
    assert calls == [1]
    res = pipe.ingest(_Block())
    assert res.is_err
    assert res.danger_err == PipelineError.Halted
    stops = [e for e in sub.drain() if isinstance(e, PipelineStopped)]
    assert len(stops) == 1
    assert stops[0].reason == "device_fault"
    assert stops[0].hint == "check cable"
    h.close()


# frob:ticket 01M6W7R36G6BYYB4RBC60ZNFTD
# frob:tests python/sadi/core/pipeline.py::AcquisitionPipeline._halt
# frob:tests python/sadi/core/pipeline.py::AcquisitionPipeline.halted
# frob:tests python/sadi/core/pipeline.py::AcquisitionPipeline._on_wal_failure
@pytest.mark.parametrize("code", [errno.ENOSPC, errno.EIO])
def test_disk_error_halts_loudly_and_display_never_exceeds_wal(tmp_path: Path, code: int) -> None:
    """After an fsync error nothing undurable is shown, acquisition stops, ingest refuses."""
    h = _open(tmp_path)
    stopped = threading.Event()
    pipe = AcquisitionPipeline(h, _config(), stop_device=stopped.set)
    sub = pipe.bus.subscribe("t")
    assert pipe.ingest(_Block()).is_ok
    assert h.wait_durable(1, WAIT_S).is_ok
    pipe.pump()
    failpoints.configure({"wal.fsync.before": f"once:error:{code}"})
    for _ in range(3):
        pipe.ingest(_Block())
    assert stopped.wait(WAIT_S)
    pipe.pump()
    assert pipe.halted
    refused = pipe.ingest(_Block())
    assert refused.is_err
    assert refused.danger_err == PipelineError.Halted
    events: list[object] = []
    deadline = time.monotonic() + WAIT_S
    while not any(isinstance(e, PipelineStopped) for e in events) and time.monotonic() < deadline:
        events += sub.drain()  # PipelineStopped is published just after the device stops
        time.sleep(0.01)
    stops = [e for e in events if isinstance(e, PipelineStopped)]
    assert len(stops) == 1
    assert stops[0].reason.startswith("store_")
    assert stops[0].hint
    shown = {f.raw_seq for f in _frames(events)}
    assert shown <= _wal_raw_seqs(tmp_path)
    assert 1 in shown
    h.close()
    assert shown <= _wal_raw_seqs(tmp_path)


# frob:ticket 01M6W7R36G6BYYB4RBC60ZNFTD
# frob:tests python/sadi/core/pipeline.py::AcquisitionPipeline.ingest
def test_backpressure_halts_and_holds_block_with_caller(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A full WAL queue returns Backpressure, halts acquisition, shows nothing undurable."""
    h = _open(tmp_path, queue_max_items=1, submit_timeout_s=0.05, batch_max_records=1)
    gate = _Gate(durable.fsync_file)
    monkeypatch.setattr(durable, "fsync_file", gate)
    stopped = threading.Event()
    pipe = AcquisitionPipeline(h, _config(), stop_device=stopped.set)
    sub = pipe.bus.subscribe("t")
    results = []
    assert pipe.ingest(_Block()).is_ok
    assert gate.entered.wait(WAIT_S)
    for _ in range(4):
        results.append(pipe.ingest(_Block()))
        if results[-1].is_err:
            break
    err = results[-1].danger_err
    assert isinstance(err, Backpressure)
    assert pipe.halted
    assert stopped.is_set()
    assert pipe.pump() == 0
    assert _frames(sub.drain()) == []
    gate.release.set()
    h.close()


# frob:ticket 01M6W7R36G6BYYB4RBC60ZNFTD
# frob:tests python/sadi/core/pipeline.py::AcquisitionPipeline.tick
def test_tick_stall_halts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No durable progress past the stall timeout halts acquisition via tick()."""
    clock = _Clock()
    h = _open(tmp_path, clock=clock, stall_timeout_s=5.0)
    gate = _Gate(durable.fsync_file)
    monkeypatch.setattr(durable, "fsync_file", gate)
    pipe = AcquisitionPipeline(h, _config(), stop_device=lambda: None)
    sub = pipe.bus.subscribe("t")
    assert pipe.ingest(_Block()).is_ok
    assert gate.entered.wait(WAIT_S)
    assert pipe.tick().is_ok
    clock.now = 6.0
    res = pipe.tick()
    assert res.is_err
    assert pipe.halted
    assert any(isinstance(e, PipelineStopped) for e in sub.drain())
    gate.release.set()
    h.close()


# frob:ticket 01M6W7R36G6BYYB4RBC60ZNFTD
# frob:tests python/sadi/core/pipeline.py::AcquisitionPipeline._release
def test_analysis_failure_does_not_touch_raw(tmp_path: Path) -> None:
    """A block the detector rejects is still saved; later blocks keep flowing."""
    h = _open(tmp_path)
    pipe = AcquisitionPipeline(h, _config())
    sub = pipe.bus.subscribe("t")
    assert pipe.mark_load_change().is_ok
    assert pipe.ingest(_Block(nan=True)).is_ok
    assert pipe.ingest(_Block()).is_ok
    assert h.wait_durable(3, WAIT_S).is_ok
    pipe.pump()
    events = sub.drain()
    assert any(isinstance(e, AnalysisFailed) for e in events)
    assert len(_frames(events)) == 2
    assert not pipe.halted
    h.close()
    assert _wal_raw_seqs(tmp_path) == {2, 3}


# frob:ticket 01M6W7R36G6BYYB4RBC60ZNFTD
# frob:tests python/sadi/core/pipeline.py::AcquisitionPipeline._release
def test_analysis_crash_is_contained(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An exception inside analysis is logged and reported, never propagated to acquisition."""
    h = _open(tmp_path)
    pipe = AcquisitionPipeline(h, _config())
    sub = pipe.bus.subscribe("t")

    def boom(*_a: object, **_k: object) -> object:
        """Simulate an analysis bug."""
        raise RuntimeError("bug")

    monkeypatch.setattr(pipe._detector, "push", boom)  # noqa: SLF001
    assert pipe.ingest(_Block()).is_ok
    assert h.wait_durable(1, WAIT_S).is_ok
    assert pipe.pump() == 1
    failed = [e for e in sub.drain() if isinstance(e, AnalysisFailed)]
    assert len(failed) == 1
    assert "bug" in failed[0].reason
    h.close()


# frob:ticket 01M6W7R36G6BYYB4RBC60ZNFTD
# frob:tests python/sadi/core/pipeline.py::AcquisitionPipeline.mark_load_change
# frob:tests python/sadi/core/pipeline.py::AcquisitionPipeline.close_point
# frob:tests python/sadi/core/pipeline.py::AcquisitionPipeline.force_early
def test_settle_state_and_result_updates(tmp_path: Path) -> None:
    """A flat LVDT after a load change settles; close_point emits a ResultUpdate."""
    h = _open(tmp_path)
    pipe = AcquisitionPipeline(h, _config())
    sub = pipe.bus.subscribe("t")
    assert pipe.mark_load_change().is_ok
    for _ in range(3):
        assert pipe.ingest(_Block()).is_ok
    assert pipe.close_point().is_ok
    assert pipe.force_early().is_ok  # settle auto-opens the next point: it is force-closed
    assert h.wait_durable(6, WAIT_S).is_ok
    pipe.pump()
    events = sub.drain()
    states = [e.status.state for e in events if isinstance(e, SettleUpdate)]
    assert states[-1] is SettleState.SETTLED
    results = [e for e in events if isinstance(e, ResultUpdate)]
    assert len(results) == 2  # settled close + the auto-opened point force-closed
    assert results[0].record.settled
    assert results[1].record.forced_early
    assert sum(isinstance(e, AnalysisFailed) for e in events) == 0
    h.close()
    types = [r.danger_ok.type for r in WalReader(tmp_path / "wal").records() if r.is_ok]
    assert types.count(int(RecordType.MARKER)) == 3


# frob:ticket 01M6W7R36G6BYYB4RBC60ZNFTD
# frob:tests python/sadi/core/pipeline.py::AcquisitionPipeline.ingest
def test_bad_block_is_refused_without_halting(tmp_path: Path) -> None:
    """A malformed block is an input error: nothing enqueued, acquisition continues."""
    h = _open(tmp_path)
    pipe = AcquisitionPipeline(h, _config())
    bad = _Block()
    bad.raw = bad.raw[:-1]
    res = pipe.ingest(bad)
    assert res.is_err
    assert res.danger_err == PipelineError.BadBlock
    assert not pipe.halted
    assert h.enqueued_seq == 0
    h.close()


# frob:ticket 01M6WJT02NYTS67SGG3W7KAMYM
# frob:tests python/sadi/core/pipeline.py::AcquisitionPipeline.ingest
def test_dropped_bytes_are_durably_recorded_as_raw_junk(tmp_path: Path) -> None:
    """A block with dropped bytes keeps every received byte as a durable RAW_JUNK record."""
    h = _open(tmp_path)
    pipe = AcquisitionPipeline(h, _config())
    blk = _Block()
    blk.raw = blk.raw + b"\xde\xad\xbe"  # junk makes the length unaligned
    blk.dropped_bytes = 3
    res = pipe.ingest(blk)
    assert res.is_ok
    assert h.wait_durable(res.danger_ok, WAIT_S).is_ok
    recs = [r.danger_ok for r in WalReader(tmp_path / "wal").records() if r.is_ok]
    junk = [r for r in recs if r.type == int(RecordType.RAW_JUNK)]
    assert len(junk) == 1
    dec = decode_raw_junk(junk[0].payload)
    assert dec.is_ok
    assert dec.danger_ok.data == blk.raw
    assert dec.danger_ok.reason == 1
    assert not pipe.halted
    h.close()


# frob:ticket 01M6W7R36G6BYYB4RBC60ZNFTD
# frob:tests python/sadi/core/pipeline.py::Subscription
# frob:tests python/sadi/core/pipeline.py::Subscription.dropped
# frob:tests python/sadi/core/pipeline.py::Bus.publish
def test_slow_subscriber_loses_only_derived_events(tmp_path: Path) -> None:
    """A tiny, never-drained subscription drops oldest events; raw saving is unaffected."""
    h = _open(tmp_path)
    bus = Bus()
    slow = bus.subscribe("slow", depth=2)
    fast = bus.subscribe("fast")
    pipe = AcquisitionPipeline(h, _config(), bus)
    for _ in range(5):
        assert pipe.ingest(_Block()).is_ok
    assert h.wait_durable(5, WAIT_S).is_ok
    pipe.pump()
    assert slow.dropped == 10 - 2  # 5 frames + 5 settle updates, 2 kept
    assert len(slow.drain()) == 2
    assert len(_frames(fast.drain())) == 5
    h.close()
    assert _wal_raw_seqs(tmp_path) == {1, 2, 3, 4, 5}


# frob:ticket 01M6W7R36G6BYYB4RBC60ZNFTD
# frob:tests python/sadi/core/pipeline.py::AcquisitionPipeline.start
# frob:tests python/sadi/core/pipeline.py::AcquisitionPipeline.stop
def test_forwarder_thread_releases_durable_blocks(tmp_path: Path) -> None:
    """The forwarder thread delivers all blocks once durable and joins on stop()."""
    h = _open(tmp_path)
    pipe = AcquisitionPipeline(h, _config())
    sub = pipe.bus.subscribe("t")
    pipe.start()
    pipe.start()  # idempotent
    for _ in range(6):
        assert pipe.ingest(_Block()).is_ok
    deadline = time.monotonic() + WAIT_S
    while pipe.pending_count() and time.monotonic() < deadline:
        time.sleep(0.01)
    pipe.stop()
    assert [f.raw_seq for f in _frames(sub.drain())] == [1, 2, 3, 4, 5, 6]
    assert h.close().is_ok


def test_writer_error_type_is_exposed(tmp_path: Path) -> None:
    """Refusals are the typed writer errors (with a UI hint), not strings."""
    h = _open(tmp_path)
    assert h.close().is_ok
    pipe = AcquisitionPipeline(h, _config())
    res = pipe.ingest(_Block())
    assert isinstance(res.danger_err, WriterError)
    assert res.danger_err.hint


# frob:ticket 01M715VW4GNGBM7CM75ZFZ58XG
# frob:tests python/sadi/store/writer_thread.py::WriterHandle.wait_durable
# frob:tests python/sadi/store/wal.py::WalWriter.wait_durable
def test_wait_durable_poll_timeout_is_not_logged_at_error(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An expected wait_durable poll timeout logs below ERROR; closed-writer failures stay ERROR."""
    h = _open(tmp_path)
    with caplog.at_level("DEBUG", logger="sadi.store.writer_thread"):
        res = h.wait_durable(10_000, 0.05)
    assert res.is_err
    assert isinstance(res.danger_err, Stalled)
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert any(r.levelno == logging.DEBUG for r in caplog.records)
    caplog.clear()
    monkeypatch.setattr(h._wal, "wait_durable", lambda *_a: Err(WalClosed()))
    with caplog.at_level("DEBUG", logger="sadi.store.writer_thread"):
        assert h.wait_durable(1, 0.05).is_err
    assert [r for r in caplog.records if r.levelno >= logging.ERROR]
    h.close()
