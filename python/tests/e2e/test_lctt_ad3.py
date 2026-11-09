"""Full LCTT flow with the AD3 (fake backend in CI) producing every test voltage."""

# frob:ticket 01M6Z32CP3XANNZ4ZRNGHQ8PEY
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from sadi.bench.lctt_source import MAX_SAFE_V, Ad3Source, AdcModel, Segment, ramp_segments
from sadi.core.results import ResultValue
from sadi.labs.lctt.export_csv import export_csv, read_file
from sadi.labs.lctt.live import LiveConfig, LiveEvent, LoadPoint, recompute
from sadi.labs.lctt.loading import SHORT_L0_M
from sadi.labs.lctt.saturation import SaturationConfig, check_saturation
from sadi.labs.lctt.settle_stream import SettleState
from sadi.labs.lctt.slip import SlipConfig, detect_slip
from sadi.logging_setup import get_logger
from sadi.store.records import RecordType
from sadi.store.session import resume_session
from sadi.store.wal import WalReader
from tests.e2e.ad3_flow import (
    BASE_HEIGHT_M,
    E_TRUE,
    N_POINTS,
    PACKET_LEN,
    RATE_HZ,
    SLOPE_M_PER_V,
    TARE_V,
    Flow,
    make_fake,
    run_full,
)
from tests.labs.lctt.test_export_csv import _session

_log = get_logger("tests.e2e.lctt_ad3")

NOW = datetime(2026, 11, 8, 15, 30, 0, tzinfo=UTC)
KILLEE = Path(__file__).with_name("killee_ad3.py")
READY_TIMEOUT_S = 60.0


@pytest.fixture
def flow(tmp_path: Path) -> Flow:
    """One complete flow on the fake AD3, device always closed."""
    be = make_fake()
    dev = be.open(0).danger_ok
    try:
        return run_full(be, dev, tmp_path / "wal")
    finally:
        assert be.close(dev).is_ok


def _values(events: list[LiveEvent]) -> dict[str, ResultValue]:
    """Recompute the result set from `events` and index it by name."""
    res = recompute(events, LiveConfig())
    assert res.is_ok, res
    return {v.name: v for v in res.danger_ok.values}


# frob:tests python/sadi/bench/lctt_source.py::Ad3Source.stream
# frob:tests python/sadi/labs/lctt/live.py::recompute
def test_full_flow_recovers_calibration_and_modulus(flow: Flow) -> None:
    """Calibration slope, tare and the elastic modulus come back from AD3 volts alone."""
    vals = _values(flow.events)
    assert vals["slope"].value == pytest.approx(SLOPE_M_PER_V, rel=1e-3)
    assert vals["intercept"].value == pytest.approx(BASE_HEIGHT_M, abs=1e-5)
    assert vals["calibration_r2"].value > 0.9999
    assert vals["tare"].value == pytest.approx(TARE_V, abs=1e-4)
    assert vals["E"].value == pytest.approx(E_TRUE, rel=0.01)
    assert vals["r2"].value > 0.999
    assert sum(isinstance(e, LoadPoint) for e in flow.events) == N_POINTS
    # Uncertainty budget: every reported value carries a finite, small standard uncertainty.
    assert 0 < vals["E"].std_unc < 0.05 * vals["E"].value
    assert 0 < vals["slope"].std_unc < 0.01 * vals["slope"].value


# frob:tests python/sadi/bench/lctt_source.py::Ad3Source.to_block
def test_every_stimulus_stays_within_one_volt(flow: Flow) -> None:
    """Nothing the AD3 produced exceeds the 1 V hardware-test amplitude budget."""
    peak = max(float(np.abs(v).max()) for v in flow.volts)
    assert peak <= MAX_SAFE_V


# frob:tests python/sadi/core/pipeline.py::AcquisitionPipeline.ingest
def test_no_data_loss_between_source_and_wal(flow: Flow) -> None:
    """Every AD3 block is in the WAL byte for byte, in order, with no junk or gaps."""
    raws = [r for r in flow.records if r.type == int(RecordType.RAW_BLOCK)]
    junk = [r for r in flow.records if r.type == int(RecordType.RAW_JUNK)]
    assert not junk
    assert len(raws) == len(flow.source_raw)
    for rec, sent in zip(raws, flow.source_raw, strict=True):
        assert rec.payload.endswith(sent)
        assert len(sent) % PACKET_LEN == 0
    seqs = [r.seq for r in flow.records]
    assert seqs == sorted(seqs)


# frob:tests python/sadi/core/pipeline.py::AcquisitionPipeline.mark_load_change
def test_live_stream_loads_then_settles_each_point(flow: Flow) -> None:
    """The live bus reports LOADING then SETTLED, and one settled result per held point."""
    states = [s.state for s in flow.statuses]
    assert states[0] is SettleState.LOADING
    assert SettleState.SETTLED in states
    assert states[-1] is SettleState.SETTLED
    assert len(flow.results) == N_POINTS + 1  # ramp plus unload
    assert all(r.settled and not r.forced_early for r in flow.results[:N_POINTS])


# frob:tests python/sadi/labs/lctt/export_csv.py::export_csv
def test_export_is_atomic_numbered_and_never_overwrites(flow: Flow, tmp_path: Path) -> None:
    """Two exports of the AD3 session get distinct numbered files and read back the same E."""
    handle = _session(tmp_path / "root")
    first = export_csv(handle, flow.events, date=NOW, operator="ad3")
    assert first.is_ok, first
    before = hashlib.sha256(first.danger_ok.path.read_bytes()).hexdigest()
    second = export_csv(handle, flow.events, date=NOW, operator="ad3")
    assert second.is_ok, second
    assert second.danger_ok.path != first.danger_ok.path
    assert hashlib.sha256(first.danger_ok.path.read_bytes()).hexdigest() == before
    leftovers = [p for p in first.danger_ok.path.parent.iterdir() if p.suffix == ".tmp"]
    assert not leftovers
    doc = read_file(first.danger_ok.path)
    assert doc.is_ok, doc
    assert len(doc.danger_ok.rows) == N_POINTS
    assert doc.danger_ok.get_float("E (Pa)") == pytest.approx(E_TRUE, rel=0.01)


# frob:tests python/sadi/labs/lctt/slip.py::detect_slip
def test_slip_like_glitch_is_detected_and_clean_hold_is_not(tmp_path: Path) -> None:
    """A step injected mid-hold on the AD3 is reported as slip; a clean hold reports none."""
    be = make_fake(seed=3)
    dev = be.open(0).danger_ok
    src = Ad3Source(be, dev, rate_hz=RATE_HZ)
    try:
        level = 0.4
        clean = src.stream([Segment(lvdt_v=level, n=200)]).danger_ok[:, 0]
        glitch = src.stream(
            [Segment(lvdt_v=level, n=100), Segment(lvdt_v=level + 0.004, n=100)]
        ).danger_ok[:, 0]
    finally:
        src.stop()
        assert be.close(dev).is_ok
    times = [0.001 + i / RATE_HZ for i in range(200)]
    to_strain = lambda v: [SLOPE_M_PER_V * (x - TARE_V) / SHORT_L0_M for x in v]  # noqa: E731
    # A quiet hold quantises to a near-constant code stream, so the MAD noise estimate collapses
    # to zero and 1-LSB flicker looks like slip. The ADC cannot resolve below one LSB, so that is
    # the physical noise floor (frob:ticket FMCPAK6); the 4 mV glitch is ~26 LSB and still detected.
    lsb_v = 2 * AdcModel().full_scale_v / 2**16
    cfg = SlipConfig(noise_floor=SLOPE_M_PER_V * lsb_v / SHORT_L0_M)
    ok = detect_slip(times, to_strain(clean), 0.0, config=cfg)
    bad = detect_slip(times, to_strain(glitch), 0.0, config=cfg)
    assert ok.is_ok and bad.is_ok
    assert not ok.danger_ok.events
    assert len(bad.danger_ok.events) == 1
    assert 95 <= bad.danger_ok.events[0].index <= 105


# frob:tests python/sadi/core/pipeline.py::AcquisitionPipeline.mark_load_change
def test_creeping_hold_is_not_declared_settled(tmp_path: Path) -> None:
    """A steadily rising hold on the AD3 keeps the point CREEPING, never SETTLED."""
    from tests.e2e.ad3_flow import FlowRunner

    be = make_fake(seed=4)
    dev = be.open(0).danger_ok
    runner = FlowRunner(Ad3Source(be, dev, rate_hz=RATE_HZ), tmp_path / "wal")
    try:
        assert runner.pipe.mark_load_change().is_ok
        runner.feed(ramp_segments((0.2, 0.7), (0.0, 0.0), steps=30, n_each=100))
    finally:
        flow = runner.finish()
        runner.src.stop()
        assert be.close(dev).is_ok
    assert flow.statuses[-1].state is SettleState.CREEPING


# frob:tests python/sadi/labs/lctt/saturation.py::check_saturation
def test_saturation_flag_follows_ad3_level() -> None:
    """A 0.9 V level trips a 0.8 V threshold and a 0.5 V level does not."""
    be = make_fake(seed=5)
    dev = be.open(0).danger_ok
    src = Ad3Source(be, dev, rate_hz=RATE_HZ)
    try:
        hi = src.stream([Segment(lvdt_v=0.9, n=100)]).danger_ok[:, 0]
        lo = src.stream([Segment(lvdt_v=0.5, n=100)]).danger_ok[:, 0]
    finally:
        src.stop()
        assert be.close(dev).is_ok
    cfg = SaturationConfig(threshold_v=0.8)
    assert check_saturation(0, hi.tolist(), cfg).danger_ok.saturated
    assert not check_saturation(1, lo.tolist(), cfg).danger_ok.saturated


# frob:tests python/sadi/bench/lctt_source.py::Ad3Source.sine_amplitude
def test_lvdt_sine_amplitude_round_trips_through_the_adc() -> None:
    """inject_lvdt's sine is read back through the ADC model at the commanded amplitude."""
    be = make_fake(seed=6)
    dev = be.open(0).danger_ok
    src = Ad3Source(be, dev, rate_hz=100_000.0)
    try:
        got = src.sine_amplitude(0.5)
    finally:
        src.stop()
        assert be.close(dev).is_ok
    assert got.is_ok
    assert got.danger_ok == pytest.approx(0.5, rel=0.01)


# frob:tests python/sadi/bench/lctt_source.py::Ad3Source.dwell
def test_over_budget_stimulus_is_refused_before_touching_the_device() -> None:
    """A level above the 1 V budget is a programmer error and never reaches the AD3."""
    be = make_fake()
    dev = be.open(0).danger_ok
    src = Ad3Source(be, dev)
    try:
        with pytest.raises(ValueError, match="safety limit"):
            src.dwell(Segment(lvdt_v=1.5, n=10))
    finally:
        assert be.close(dev).is_ok


def _digest(root: Path) -> str:
    """Hash every file (relative name and bytes) under `root`."""
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(root)).encode())
            h.update(p.read_bytes())
    return h.hexdigest()


# frob:tests python/sadi/store/session.py::resume_session
def test_sigkill_then_resume_continues_the_ad3_run(tmp_path: Path) -> None:
    """SIGKILL during AD3 acquisition: v001 stays intact and v002 completes a full flow."""
    root, ready = tmp_path / "data", tmp_path / "ready"
    env = dict(os.environ)
    pkg_root = str(Path(__file__).resolve().parents[2])
    env["PYTHONPATH"] = pkg_root + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.Popen(
        [sys.executable, str(KILLEE), str(root), str(ready)],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )  # fmt: skip
    try:
        deadline = time.monotonic() + READY_TIMEOUT_S
        while not ready.exists() and proc.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        assert ready.exists(), "killee never became ready"
        proc.kill()
    finally:
        proc.kill()
        proc.wait()
    v1 = Path(ready.read_text())
    assert WalReader.scan(v1 / "wal").is_ok
    raw_before = [
        r.danger_ok for r in WalReader(v1 / "wal").records()
        if r.is_ok and r.danger_ok.type == int(RecordType.RAW_BLOCK)
    ]  # fmt: skip
    assert len(raw_before) >= 5
    digest = _digest(v1)

    refused = resume_session(v1)
    if refused.is_ok:
        refused.danger_ok.close()
    resumed = refused if refused.is_ok else resume_session(v1, recover_stale=True)
    assert resumed.is_ok, resumed
    handle = resumed.danger_ok
    be = make_fake(seed=9)
    dev = be.open(0).danger_ok
    try:
        assert handle.path.name.endswith(".v002")
        assert handle.manifest.parent == v1.name
        assert handle.manifest.parent_last_seq is not None
        assert handle.manifest.parent_last_seq >= len(raw_before)
        flow2 = run_full(be, dev, handle.path / "wal")
    finally:
        be.close(dev)
        handle.close()
    assert _values(flow2.events)["E"].value == pytest.approx(E_TRUE, rel=0.01)
    assert any(r.type == int(RecordType.RAW_BLOCK) for r in flow2.records)
    assert _digest(v1) == digest, "resume modified the killed parent version"
