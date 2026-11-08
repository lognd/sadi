"""Synchronous sim -> pipeline -> WAL runner used by the e2e fault scenarios."""

# frob:ticket 01M6W7RB61AEQRD899AWKK27QJ
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import sadi_py
from numpy.typing import NDArray

from sadi.core.pipeline import (
    AcquisitionPipeline,
    PipelineConfig,
    ResultUpdate,
    SettleUpdate,
)
from sadi.labs.lctt.settle import SettleConfig
from sadi.labs.lctt.settle_stream import PointRecord, StreamConfig, StreamStatus
from sadi.logging_setup import get_logger
from sadi.store.records import Record, RecordType
from sadi.store.wal import WalConfig, WalReader
from sadi.store.writer_thread import WriterHandle

_log = get_logger("tests.e2e.harness")

SIM_RATE_HZ = 50_000.0
PACKET_LEN = 612
BLOCK_SAMPLES = 50
BATCH_BLOCKS = 10
ANALYSIS_RATE_HZ = SIM_RATE_HZ
BATCH_S = BATCH_BLOCKS * BLOCK_SAMPLES / SIM_RATE_HZ
# Strain per volt of LVDT signal: gauge strain step / LVDT displacement scale of the sim.
STRAIN_PER_V = 2.114583e-3 / 0.08313
SETTLE = SettleConfig(window_s=0.02, threshold=1.0, min_dwell_s=0.03, min_points=5)


@dataclass(frozen=True)
class ByteDrop:
    """Drop `count` bytes from the raw stream of block number `block` (0-based)."""

    block: int
    count: int


class _Batch:
    """Several source blocks joined as one pipeline block at the full 50 kHz device rate."""

    def __init__(self, blocks: list[Any], drop: int = 0) -> None:
        """Join `blocks`; with `drop` > 0 cut that many bytes from the middle of the raw."""
        raw = b"".join(bytes(b.raw) for b in blocks)
        volts = np.concatenate([np.array(b.volts) for b in blocks])
        counts = np.concatenate([np.array(b.msg_count) for b in blocks])
        if drop:
            cut = len(raw) // 2
            raw = raw[:cut] + raw[cut + drop :]
        self.raw = raw
        self.volts = volts
        self.msg_count = counts
        self.n_samples = len(self.volts)
        self.dropped_bytes = drop
        self.gap_events = 1 if drop else 0


@dataclass
class Run:
    """Everything one scenario run produced, for assertions."""

    volts: NDArray[np.float64]
    source_raw: list[bytes]
    ingested_raw: list[bytes] = field(default_factory=list)
    analysed: list[NDArray[np.float64]] = field(default_factory=list)
    statuses: list[StreamStatus] = field(default_factory=list)
    results: list[PointRecord] = field(default_factory=list)
    records: list[Record] = field(default_factory=list)
    dropped_bytes: int = 0
    gap_events: int = 0
    slip_count: int = 0

    def of_type(self, rtype: RecordType) -> list[Record]:
        """Return the WAL records of one type, in order."""
        return [r for r in self.records if r.type == int(rtype)]

    def wal_raw(self) -> list[Record]:
        """Return the raw-carrying WAL records (RAW_BLOCK and RAW_JUNK) in append order."""
        keep = (int(RecordType.RAW_BLOCK), int(RecordType.RAW_JUNK))
        return [r for r in self.records if r.type in keep]

    @property
    def analysis_volts(self) -> NDArray[np.float64]:
        """The volts the pipeline analysed, all channels."""
        return np.concatenate(self.analysed)

    @property
    def times(self) -> NDArray[np.float64]:
        """Sample times in seconds for `volts`."""
        return np.arange(len(self.volts)) / SIM_RATE_HZ


def run_scenario(
    scenario: dict[str, Any],
    wal_dir: Path,
    *,
    duration_s: float,
    load_at_s: float,
    seed: int = 1,
    drops: tuple[ByteDrop, ...] = (),
) -> Run:
    """Drive `scenario` for `duration_s` of sim time, marking the load change at `load_at_s`."""
    session, ctl = sadi_py.sim.open(scenario, seed)
    wal_dir.mkdir(parents=True, exist_ok=True)
    opened = WriterHandle.open(wal_dir, uuid.UUID(int=11), 1, WalConfig())
    assert opened.is_ok, opened
    writer = opened.danger_ok
    cfg = PipelineConfig(
        stream=StreamConfig(settle=SETTLE), sample_rate_hz=ANALYSIS_RATE_HZ, packet_len=PACKET_LEN
    )
    pipe = AcquisitionPipeline(writer, cfg)
    sub = pipe.bus.subscribe("e2e", depth=100_000)
    run = Run(volts=np.zeros((0, 4)), source_raw=[])
    chunks: list[NDArray[np.float64]] = []
    by_block = {d.block: d.count for d in drops}
    session.connect()
    session.start(sadi_py.AdcMode.DLL_COMPATIBLE)

    def feed(blocks: list[Any], index: int) -> None:
        run.source_raw.append(b"".join(bytes(b.raw) for b in blocks))
        chunks.extend(np.array(b.volts) for b in blocks)
        drop = by_block.get(index, 0)
        batch = _Batch(blocks, drop)
        run.dropped_bytes += batch.dropped_bytes
        run.gap_events += batch.gap_events
        run.ingested_raw.append(batch.raw)
        run.analysed.append(batch.volts)
        assert pipe.ingest(batch).is_ok

    marked = False
    batches = round(duration_s / BATCH_S)
    for index in range(batches):
        if not marked and index * BATCH_S >= load_at_s:
            assert pipe.mark_load_change().is_ok
            marked = True
        blocks = [session.read_block() for _ in range(BATCH_BLOCKS)]
        if index == batches - 1:
            blocks.append(session.stop())  # the trailing block rides with the last batch
        feed(blocks, index)
        _wait_durable(writer, pipe)
    assert pipe.close_point().is_ok
    _wait_durable(writer, pipe)
    pipe.stop()
    writer.close()
    run.slip_count = int(ctl.slip_count)
    for ev in sub.drain():
        if isinstance(ev, SettleUpdate):
            run.statuses.append(ev.status)
        elif isinstance(ev, ResultUpdate):
            run.results.append(ev.record)
    run.volts = np.concatenate(chunks)
    run.records = [r.danger_ok for r in WalReader(wal_dir).records() if r.is_ok]
    _log.info("scenario done: %d samples, %d records", len(run.volts), len(run.records))
    return run


def _wait_durable(writer: WriterHandle, pipe: AcquisitionPipeline) -> None:
    """Block until everything enqueued is durable, then release it to analysis."""
    assert writer.wait_durable(writer.enqueued_seq, 10.0).is_ok
    pipe.pump()
