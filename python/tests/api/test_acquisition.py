"""Tests for the acquisition driver: block flow to the WAL, tick timer, load chain, faults."""

# frob:ticket 01M6WJT055W0QPZYNF862E6T8C
from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

import numpy as np
from typani import Err, Ok, Result

from sadi.api.acquisition import (
    AcquisitionDriver,
    AcquisitionError,
    DriverFault,
    LoadChain,
    LoadStep,
)
from sadi.core.pipeline import AcquisitionPipeline, PipelineConfig, PipelineStopped
from sadi.labs.lctt.settle import SettleConfig
from sadi.labs.lctt.settle_stream import StreamConfig
from sadi.store.records import RecordType
from sadi.store.wal import WalConfig, WalReader
from sadi.store.writer_thread import WriterHandle

PACKET = 8
N = 50
WAIT_S = 10.0


class _Block:
    def __init__(self) -> None:
        self.volts = np.full((N, 4), 1.0)
        self.n_samples = N
        self.raw = bytes(range(PACKET)) * N
        self.msg_count = np.arange(N, dtype=np.uint32)
        self.dropped_bytes = 0


class _Source:
    """Fake device: yields `count` blocks, then idles; trailing blocks come from stop."""

    def __init__(self, count: int, tail: int = 0, fault: str | None = None) -> None:
        self.left = count
        self.tail = tail
        self.fault = fault

    def next_block(self, timeout: float | None = 0.0) -> Result[Any, Any]:
        if self.left:
            self.left -= 1
            return Ok(_Block())
        if self.fault is not None:
            return Err(self.fault)
        time.sleep(min(timeout or 0.01, 0.01))
        return Ok(None)

    def stop_streaming(self) -> Result[list[Any], Any]:
        return Ok([_Block() for _ in range(self.tail)])


def _pipe(tmp_path: Path) -> tuple[AcquisitionPipeline, WriterHandle]:
    wal = tmp_path / "wal"
    wal.mkdir()
    res = WriterHandle.open(wal, uuid.UUID(int=7), 1, WalConfig())
    assert res.is_ok, res
    settle = SettleConfig(window_s=0.05, threshold=1.0, min_dwell_s=0.05, min_points=5)
    cfg = PipelineConfig(
        stream=StreamConfig(settle=settle), sample_rate_hz=1000.0, packet_len=PACKET
    )
    return AcquisitionPipeline(res.danger_ok, cfg), res.danger_ok


def _raw_count(tmp_path: Path) -> int:
    return sum(
        1
        for r in WalReader(tmp_path / "wal").records()
        if r.is_ok and r.danger_ok.type == int(RecordType.RAW_BLOCK)
    )


def _wait(pred: Any) -> None:
    end = time.monotonic() + WAIT_S
    while not pred():
        assert time.monotonic() < end, "timed out"
        time.sleep(0.01)


# frob:tests python/sadi/api/acquisition.py::AcquisitionDriver.start
# frob:tests python/sadi/api/acquisition.py::AcquisitionDriver.ingested
# frob:tests python/sadi/api/acquisition.py::AcquisitionDriver.running
# frob:tests python/sadi/api/acquisition.py::AcquisitionDriver.stop
# frob:tests python/sadi/api/acquisition.py::AcquisitionDriver._acquire_loop
# frob:tests python/sadi/api/acquisition.py::AcquisitionDriver._ingest
# frob:tests python/sadi/api/acquisition.py::AcquisitionDriver._tick_loop
def test_every_block_and_tail_reaches_the_wal(tmp_path: Path) -> None:
    pipe, wal = _pipe(tmp_path)
    drv = AcquisitionDriver(_Source(5, tail=2), pipe, tick_interval_s=0.01, poll_s=0.01)
    assert drv.start().is_ok
    assert drv.running
    assert drv.start() == Err(AcquisitionError.AlreadyRunning)
    _wait(lambda: drv.ingested == 5)
    assert drv.stop() == Ok(2)
    assert drv.fault is None
    assert drv.stop() == Err(AcquisitionError.NotRunning)
    wal.close()
    assert _raw_count(tmp_path) == 7
    assert drv.ingested == 7


# frob:tests python/sadi/api/acquisition.py::AcquisitionDriver.next_load
# frob:tests python/sadi/api/acquisition.py::LoadChain.peek
def test_load_chain_writes_markers_in_order(tmp_path: Path) -> None:
    pipe, wal = _pipe(tmp_path)
    chain = LoadChain(steps=(LoadStep(label="a", mass_kg=1.0), LoadStep(label="b", mass_kg=2.0)))
    drv = AcquisitionDriver(_Source(0), pipe, chain=chain)
    assert drv.next_load().unwrap().label == "a"
    assert drv.next_load().unwrap().label == "b"
    assert drv.next_load() == Err(AcquisitionError.ChainExhausted)
    assert chain.applied == 2
    assert AcquisitionDriver(_Source(0), pipe).next_load() == Err(AcquisitionError.NoChain)
    wal.close()
    markers = [
        r
        for r in WalReader(tmp_path / "wal").records()
        if r.is_ok and r.danger_ok.type == int(RecordType.MARKER)
    ]
    assert len(markers) == 2


# frob:tests python/sadi/api/acquisition.py::AcquisitionDriver.fault
# frob:tests python/sadi/api/acquisition.py::AcquisitionDriver._record_fault
# frob:tests python/sadi/api/acquisition.py::AcquisitionDriver._halt_pipeline
def test_device_fault_halts_loudly_and_keeps_saved_blocks(tmp_path: Path) -> None:
    pipe, wal = _pipe(tmp_path)
    sub = pipe.bus.subscribe("t")
    drv = AcquisitionDriver(_Source(3, fault="unplugged"), pipe, tick_interval_s=0.01, poll_s=0.01)
    drv.start()
    _wait(lambda: drv.fault is not None)
    assert isinstance(drv.fault, DriverFault) and drv.fault.origin == "device"
    assert pipe.halted
    assert any(isinstance(e, PipelineStopped) for e in sub.drain())
    drv.stop()
    wal.close()
    assert _raw_count(tmp_path) == 3
