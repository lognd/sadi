"""Full-run fault scenarios: simulator -> pipeline -> real WAL, asserted against ground truth."""

# frob:ticket 01M6W7RB61AEQRD899AWKK27QJ
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray

pytest.importorskip("sadi_py", reason="native extension not built")

from sadi.labs.lctt.saturation import SaturationConfig, check_saturation
from sadi.labs.lctt.settle_stream import SettleState
from sadi.labs.lctt.slip import SlipEvent, detect_slip
from sadi.logging_setup import get_logger
from sadi.store.records import RecordType, decode_raw_junk
from tests.e2e.harness import (
    ANALYSIS_RATE_HZ,
    BATCH_S,
    SETTLE,
    STRAIN_PER_V,
    Run,
    run_scenario,
)
from tests.e2e.scenarios import (
    BASELINE,
    CLAMP_V,
    COMBINED,
    COMBINED_CLAMP_V,
    CREEP,
    CREEP_COEFF,
    CREEP_TAU_S,
    DRIFT,
    DRIFT_V_PER_S,
    DROPPED,
    DURATION_S,
    LOAD_AT_S,
    MATRIX,
    NOISE,
    NOISE_SD_V,
    SATURATION,
    SLIP,
    SLIP_T_S,
    Spec,
    scenario_dict,
)

_log = get_logger("tests.e2e.faults")

BATCHES = round(DURATION_S / BATCH_S)


def _run(spec: Spec, tmp_path: Path) -> Run:
    """Run one matrix row for the standard duration into a fresh WAL under `tmp_path`."""
    return run_scenario(
        scenario_dict(spec),
        tmp_path / "wal",
        duration_s=DURATION_S,
        load_at_s=LOAD_AT_S,
        drops=spec.drops,
    )


def _analysis(run: Run) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Return (times, LVDT volts) of the decimated stream the pipeline analysed."""
    volts = run.analysis_volts[:, 0]
    return np.arange(len(volts)) / ANALYSIS_RATE_HZ, volts


def _slip_events(run: Run) -> list[SlipEvent]:
    """Run the slip detector over the post-load hold; strain is volts above the pre-load mean."""
    t, v = _analysis(run)
    hold = t > LOAD_AT_S + 0.01
    base = float(v[t < LOAD_AT_S - 0.01].mean())
    strain = (v[hold] - base) * STRAIN_PER_V
    res = detect_slip(t[hold].tolist(), strain.tolist(), LOAD_AT_S)
    assert res.is_ok, res
    return list(res.danger_ok.events)


# frob:tests python/sadi/core/pipeline.py::AcquisitionPipeline.ingest
@pytest.mark.parametrize("spec", MATRIX + (BASELINE,), ids=lambda s: s.name)
def test_raw_is_preserved_in_the_wal(spec: Spec, tmp_path: Path) -> None:
    """Every scenario keeps each received byte in the WAL, in order, as block or junk."""
    run = _run(spec, tmp_path)
    wal = run.wal_raw()
    assert len(wal) == len(run.ingested_raw) == BATCHES
    for rec, got, sent in zip(wal, run.ingested_raw, run.source_raw, strict=True):
        if rec.type == int(RecordType.RAW_JUNK):
            assert got != sent
            junk = decode_raw_junk(rec.payload)
            assert junk.is_ok
            assert junk.danger_ok.data == got
        else:
            assert got == sent
            assert rec.payload.endswith(got)
    stopped = run.of_type(RecordType.MARKER)
    assert len(stopped) == 2  # load_applied + the closing marker


# frob:tests python/sadi/labs/lctt/settle_stream.py::StreamingSettleDetector.push
def test_noise_settles_and_matches_the_injected_sd(tmp_path: Path) -> None:
    """White noise within the threshold settles; the measured sd matches the plan within 15%."""
    run = _run(NOISE, tmp_path)
    assert run.statuses[-1].state is SettleState.SETTLED
    assert run.results and run.results[0].settled
    t, v = _analysis(run)
    assert float(v[t < LOAD_AT_S - 0.01].std()) == pytest.approx(NOISE_SD_V, rel=0.15)


# frob:tests python/sadi/labs/lctt/settle_stream.py::StreamingSettleDetector.push
def test_drift_never_settles_and_is_measured(tmp_path: Path) -> None:
    """A linear drift above the threshold keeps the point creeping and is read back within 5%."""
    run = _run(DRIFT, tmp_path)
    last = run.statuses[-1]
    assert last.state is SettleState.CREEPING
    assert run.results and not run.results[0].settled
    assert last.drift_rate is not None
    assert last.drift_rate.value == pytest.approx(DRIFT_V_PER_S, rel=0.05)
    t, v = _analysis(run)
    pre = t < LOAD_AT_S - 0.01
    assert np.polyfit(t[pre], v[pre], 1)[0] == pytest.approx(DRIFT_V_PER_S, rel=0.05)


# frob:tests python/sadi/labs/lctt/settle_stream.py::StreamingSettleDetector.push
def test_creep_settles_with_a_positive_sub_threshold_drift(tmp_path: Path) -> None:
    """Log-time creep keeps a small positive drift; the log-slope matches coeff * step within 5%."""
    run = _run(CREEP, tmp_path)
    last = run.statuses[-1]
    assert last.state is SettleState.SETTLED
    assert last.drift_rate is not None
    assert 0 < last.drift_rate.value < SETTLE.threshold
    t, v = _analysis(run)
    base = float(v[t < LOAD_AT_S - 0.01].mean())
    hold = t > LOAD_AT_S + 0.05
    x = np.log(1 + (t[hold] - LOAD_AT_S) / CREEP_TAU_S)
    step = float(v[(t > LOAD_AT_S) & (t < LOAD_AT_S + 0.001)].mean()) - base
    slope = np.polyfit(x, v[hold], 1)[0]
    # The elastic step is the zero-creep plateau of the baseline run, 1 kg => ~0.0181 V.
    elastic = _baseline_step(tmp_path / "base")
    assert step > 0
    assert slope == pytest.approx(CREEP_COEFF * elastic, rel=0.05)


def _baseline_step(tmp_path: Path) -> float:
    """Return the LVDT step (V) a clean 1 kg load produces, from a quiet reference run."""
    run = _run(BASELINE, tmp_path)
    t, v = _analysis(run)
    return float(v[t > LOAD_AT_S + 0.05].mean() - v[t < LOAD_AT_S - 0.01].mean())


# frob:tests python/sadi/labs/lctt/slip.py::detect_slip
def test_slip_step_is_flagged_at_the_injected_time(tmp_path: Path) -> None:
    """The injected slip is the only event detect_slip reports, within 10 ms and 5% of size."""
    run = _run(SLIP, tmp_path)
    assert run.slip_count == 1
    events = _slip_events(run)
    assert len(events) == 1
    assert events[0].time == pytest.approx(SLIP_T_S, abs=0.01)
    assert events[0].size == pytest.approx(0.005, rel=0.05)
    assert not _slip_events(_run(BASELINE, tmp_path / "base"))


# frob:tests python/sadi/core/pipeline.py::AcquisitionPipeline.ingest
def test_dropped_bytes_resync_with_counted_gaps(tmp_path: Path) -> None:
    """Dropped bytes become RAW_JUNK records, the counts add up, and analysis carries on."""
    run = _run(DROPPED, tmp_path)
    junk = run.of_type(RecordType.RAW_JUNK)
    assert len(junk) == len(DROPPED.drops) == run.gap_events
    assert run.dropped_bytes == sum(d.count for d in DROPPED.drops)
    assert len(run.of_type(RecordType.RAW_BLOCK)) == BATCHES - len(junk)
    lost = sum(len(s) - len(g) for s, g in zip(run.source_raw, run.ingested_raw, strict=True))
    assert lost == run.dropped_bytes
    assert run.statuses[-1].state is SettleState.SETTLED
    assert run.results and run.results[0].settled


# frob:tests python/sadi/labs/lctt/saturation.py::check_saturation
def test_saturation_clamp_is_flagged(tmp_path: Path) -> None:
    """A clamped LVDT peaks at the limit and is flagged; an unclamped run passes the 4.9 V check."""
    run = _run(SATURATION, tmp_path)
    peak = float(np.max(run.volts[:, 0]))
    assert peak == pytest.approx(CLAMP_V, abs=1e-3)
    assert peak <= CLAMP_V
    flag = check_saturation(0, run.volts[:, 0].tolist(), SaturationConfig(threshold_v=1.0))
    assert flag.is_ok
    assert flag.danger_ok.saturated
    assert "clipping" in flag.danger_ok.message
    clean = check_saturation(0, _run(BASELINE, tmp_path / "base").volts[:, 0].tolist())
    assert clean.is_ok
    assert not clean.danger_ok.saturated


# frob:tests python/sadi/labs/lctt/slip.py::detect_slip
# frob:tests python/sadi/labs/lctt/saturation.py::check_saturation
# frob:tests python/sadi/core/pipeline.py::AcquisitionPipeline.ingest
def test_combined_faults_all_surface_together(tmp_path: Path) -> None:
    """Noise + creep + slip + clamp + a dropped-byte gap in one run: each is still detected."""
    run = _run(COMBINED, tmp_path)
    assert run.slip_count == 1
    # Noise makes the detector report many small events; the injected slip is the largest.
    events = _slip_events(run)
    assert max(events, key=lambda e: e.size).time == pytest.approx(SLIP_T_S, abs=0.01)
    flag = check_saturation(0, run.volts[:, 0].tolist(), SaturationConfig(threshold_v=1.05))
    assert flag.is_ok
    assert flag.danger_ok.saturated
    assert float(np.max(run.volts[:, 0])) <= COMBINED_CLAMP_V
    assert len(run.of_type(RecordType.RAW_JUNK)) == run.gap_events == 1
    assert run.statuses[-1].state is SettleState.SETTLED
    _log.info("combined run: %d WAL records", len(run.records))
