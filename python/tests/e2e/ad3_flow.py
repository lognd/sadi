"""AD3-sourced LCTT flow: calibration, tare, load ramp, hold/creep, slip, pipeline and WAL."""

# frob:ticket 01M6Z32CP3XANNZ4ZRNGHQ8PEY
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from sadi.bench.ad3.backend import DwfBackend, OpenDevice
from sadi.bench.ad3.fake import FakeConfig, FakeDwf, ScopeCal
from sadi.bench.lctt_source import Ad3Block, Ad3Source, Segment
from sadi.core.pipeline import (
    AcquisitionPipeline,
    PipelineConfig,
    ResultUpdate,
    SettleUpdate,
)
from sadi.labs.lctt.live import CalPoint, LiveEvent, LoadPoint, SpecimenSetup, TareBlock
from sadi.labs.lctt.loading import SHORT_L0_M, STANDARD_G
from sadi.labs.lctt.settle import SettleConfig
from sadi.labs.lctt.settle_stream import PointRecord, StreamConfig, StreamStatus
from sadi.logging_setup import get_logger
from sadi.store.records import Record
from sadi.store.wal import WalConfig, WalReader
from sadi.store.writer_thread import WriterHandle

_log = get_logger("tests.e2e.ad3_flow")

RATE_HZ = 50_000.0
PACKET_LEN = 612
SETTLE = SettleConfig(window_s=0.02, threshold=1.0, min_dwell_s=0.03, min_points=5)
SLOPE_M_PER_V = 0.01  # LVDT calibration truth
BASE_HEIGHT_M = 0.05
TARE_V = 0.2
E_TRUE = 70e9
DIAMETER_M = 0.5e-3  # thin wire keeps the whole test inside the AD3 1 V budget
HANGER_KG = 0.05
MASS_STEP_KG = 0.3
N_POINTS = 8
DWELL_N = 3000  # 60 ms at 50 kHz
TAIL_N = 1500
CAL_LEVELS_V = (0.0, 0.2, 0.4, 0.6, 0.8)
NOISE_V = 2e-5


def make_fake(seed: int = 1) -> FakeDwf:
    """A fake AD3 with a little scope noise on both loopback channels."""
    cal = {0: ScopeCal(noise_v=NOISE_V), 1: ScopeCal(noise_v=NOISE_V)}
    return FakeDwf(FakeConfig(seed=seed, cal=cal))


def point_volts(k: int) -> float:
    """LVDT volts of load step `k` (1-based) for a specimen of modulus E_TRUE."""
    area = np.pi * DIAMETER_M**2 / 4.0
    stress = (k * MASS_STEP_KG + HANGER_KG) * STANDARD_G / area
    return TARE_V + (stress / E_TRUE) * SHORT_L0_M / SLOPE_M_PER_V


@dataclass
class Flow:
    """Everything one AD3-sourced flow produced, for assertions."""

    events: list[LiveEvent] = field(default_factory=list)
    source_raw: list[bytes] = field(default_factory=list)
    volts: list[NDArray[np.float64]] = field(default_factory=list)
    statuses: list[StreamStatus] = field(default_factory=list)
    results: list[PointRecord] = field(default_factory=list)
    records: list[Record] = field(default_factory=list)


class FlowRunner:
    """Pushes AD3 segments through the real pipeline into a real WAL."""

    def __init__(self, src: Ad3Source, wal_dir: Path, seed: int = 11) -> None:
        """Open the WAL writer and pipeline for `src`, subscribing to settle/result events."""
        wal_dir.mkdir(parents=True, exist_ok=True)
        opened = WriterHandle.open(wal_dir, uuid.UUID(int=seed), 1, WalConfig())
        assert opened.is_ok, opened
        self.src = src
        self.wal_dir = wal_dir
        self.writer = opened.danger_ok
        cfg = PipelineConfig(
            stream=StreamConfig(settle=SETTLE), sample_rate_hz=RATE_HZ, packet_len=PACKET_LEN
        )
        self.pipe = AcquisitionPipeline(self.writer, cfg)
        self.sub = self.pipe.bus.subscribe("ad3-flow", depth=100_000)
        self.flow = Flow()

    def feed(self, segments: list[Segment]) -> NDArray[np.float64]:
        """Drive `segments` on the AD3, ingest them as one block, return their volts."""
        got = self.src.stream(segments)
        assert got.is_ok, got
        volts = got.danger_ok
        block: Ad3Block = self.src.to_block(volts, PACKET_LEN)
        assert self.pipe.ingest(block).is_ok
        self.flow.source_raw.append(block.raw)
        self.flow.volts.append(volts)
        self.settle_durable()
        return volts

    def settle_durable(self) -> None:
        """Block until everything enqueued is durable, then release it to analysis."""
        assert self.writer.wait_durable(self.writer.enqueued_seq, 10.0).is_ok
        self.pipe.pump()

    def load_point(self, level_v: float, load_v: float, n: int = DWELL_N) -> NDArray[np.float64]:
        """Mark a load change, hold one level pair, close the point; return its volts."""
        assert self.pipe.mark_load_change().is_ok
        volts = self.feed([Segment(lvdt_v=level_v, load_v=load_v, n=n)])
        assert self.pipe.close_point().is_ok
        self.settle_durable()
        return volts

    def finish(self) -> Flow:
        """Close the pipeline and writer, collect events and the verified WAL records."""
        self.settle_durable()
        self.pipe.stop()
        self.writer.close()
        for ev in self.sub.drain():
            if isinstance(ev, SettleUpdate):
                self.flow.statuses.append(ev.status)
            elif isinstance(ev, ResultUpdate):
                self.flow.results.append(ev.record)
        self.flow.records = [r.danger_ok for r in WalReader(self.wal_dir).records() if r.is_ok]
        _log.info("flow done: %d records", len(self.flow.records))
        return self.flow


def calibrate(runner: FlowRunner) -> None:
    """Calibration stage: hold each known level on the AD3 and record (volts, height) pairs."""
    for level in CAL_LEVELS_V:
        rd = runner.src.read(level, 0.0, n=500)
        assert rd.is_ok, rd
        height = BASE_HEIGHT_M + SLOPE_M_PER_V * level
        runner.flow.events.append(CalPoint(volts=rd.danger_ok.lvdt_v, height=height))


def tare(runner: FlowRunner) -> None:
    """Zero stage: stream the unloaded level through the pipeline and record a tare block."""
    volts = runner.feed([Segment(lvdt_v=TARE_V, load_v=0.0, n=DWELL_N)])
    ch = volts[:, 0]
    runner.flow.events.append(TareBlock(mean=float(ch.mean()), sd=float(ch.std(ddof=1)), n=len(ch)))
    runner.flow.events.append(
        SpecimenSetup(diameter=DIAMETER_M, u_diameter=1e-6, hanger_kg=HANGER_KG, u_hanger_kg=1e-4)
    )


def ramp(runner: FlowRunner, points: int = N_POINTS) -> None:
    """Loading ramp: one settled hold per mass step, recorded as LoadPoint events."""
    for k in range(1, points + 1):
        volts = runner.load_point(point_volts(k), 0.05 * k)
        tail = volts[-TAIL_N:, 0]
        runner.flow.events.append(
            LoadPoint(
                point_id=f"p{k}", volts=float(tail.mean()), u_volts=2 * float(tail.std(ddof=1)),
                mass_kg=k * MASS_STEP_KG, u_mass_kg=1e-4, settled=True,
                t_since_load_s=len(volts) / RATE_HZ, volts_sd=float(tail.std(ddof=1)),
            )
        )  # fmt: skip


def run_full(be: DwfBackend, dev: OpenDevice, wal_dir: Path, points: int = N_POINTS) -> Flow:
    """Calibration, tare, load ramp and unload on the AD3; returns the finished Flow."""
    runner = FlowRunner(Ad3Source(be, dev, rate_hz=RATE_HZ), wal_dir)
    try:
        calibrate(runner)
        tare(runner)
        ramp(runner, points)
        runner.load_point(TARE_V, 0.0)  # unload back to the zero level
    finally:
        flow = runner.finish()
        runner.src.stop()
    return flow
