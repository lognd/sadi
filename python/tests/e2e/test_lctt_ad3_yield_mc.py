"""AD3-driven LCTT stages not covered elsewhere: offset yield stress and Monte Carlo checks."""

# frob:ticket 01M6Z3FR8JVXE93GMY9KKZC2KB
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from sadi.bench.lctt_source import Ad3Source
from sadi.core.results import McStatus, ResultSet, mc_crosscheck, with_mc
from sadi.labs.lctt.calibration import fit_calibration
from sadi.labs.lctt.live import (
    CalPoint,
    LiveConfig,
    LiveEvent,
    LoadPoint,
    SpecimenSetup,
    TareBlock,
    recompute,
)
from sadi.labs.lctt.loading import (
    SHORT_L0_M,
    STANDARD_G,
    LoadingInputs,
    compute_loading,
    pool_tare,
)
from sadi.labs.lctt.modulus import CurvePoint, fit_modulus
from sadi.labs.lctt.yield_ import find_yield, yield_stress
from sadi.logging_setup import get_logger
from sadi.uncertainty import Measured, Provenance
from tests.e2e.ad3_flow import (
    DIAMETER_M,
    E_TRUE,
    HANGER_KG,
    RATE_HZ,
    SLOPE_M_PER_V,
    TAIL_N,
    TARE_V,
    Flow,
    FlowRunner,
    calibrate,
    make_fake,
    ramp,
    tare,
)

_log = get_logger("tests.e2e.lctt_ad3_yield_mc")

#: Elastic to 0.3 % strain, then a flat-ish hardening branch (stress, strain in true units).
ELASTIC_STRAINS = (0.0005, 0.001, 0.0015, 0.002, 0.0025, 0.003)
PLASTIC = ((0.005, 230e6), (0.008, 245e6))
AREA = np.pi * DIAMETER_M**2 / 4.0


def _strain_volts(strain: float) -> float:
    """LVDT volts that encode `strain` on the short specimen."""
    return TARE_V + strain * SHORT_L0_M / SLOPE_M_PER_V


def _mass_kg(stress: float) -> float:
    """Hanger-excluded mass giving `stress` on the thin wire."""
    return stress * AREA / STANDARD_G - HANGER_KG


def _curve_pairs() -> list[tuple[float, float]]:
    """(strain, stress) truth for the elastic then plastic ramp."""
    return [(e, E_TRUE * e) for e in ELASTIC_STRAINS] + [(e, s) for e, s in PLASTIC]


def _plastic_ramp(runner: FlowRunner) -> None:
    """Hold each (strain, stress) pair on the AD3 and record it as a settled LoadPoint."""
    for k, (strain, stress) in enumerate(_curve_pairs(), start=1):
        volts = runner.load_point(_strain_volts(strain), min(0.05 * k, 0.9))
        tail = volts[-TAIL_N:, 0]
        runner.flow.events.append(
            LoadPoint(
                point_id=f"p{k}", volts=float(tail.mean()), u_volts=2 * float(tail.std(ddof=1)),
                mass_kg=_mass_kg(stress), u_mass_kg=1e-4, settled=True,
                t_since_load_s=len(volts) / RATE_HZ, volts_sd=float(tail.std(ddof=1)),
            )
        )  # fmt: skip


def _run(tmp_path: Path, *, plastic: bool) -> Flow:
    """Calibrate, tare and ramp (plastic or elastic-only) on the fake AD3."""
    be = make_fake()
    dev = be.open(0).danger_ok
    runner = FlowRunner(Ad3Source(be, dev, rate_hz=RATE_HZ), tmp_path / "wal")
    try:
        calibrate(runner)
        tare(runner)
        if plastic:
            _plastic_ramp(runner)
        else:
            ramp(runner, 4)
    finally:
        flow = runner.finish()
        runner.src.stop()
        be.close(dev).expect("close AD3")
    return flow


def _recompute(events: list[LiveEvent]) -> ResultSet:
    """Recompute the full result set from raw events."""
    res = recompute(events, LiveConfig())
    return res.expect("recompute")


def _expected_yield() -> float:
    """Yield stress of the true polyline against the 0.2 % offset line of slope E_TRUE."""
    (e0, s0), (e1, s1) = (ELASTIC_STRAINS[-1], E_TRUE * ELASTIC_STRAINS[-1]), PLASTIC[0]
    for (ea, sa), (eb, sb) in zip(_curve_pairs(), _curve_pairs()[1:], strict=False):
        if sa - E_TRUE * (ea - 0.002) > 0 >= sb - E_TRUE * (eb - 0.002):
            e0, s0, e1, s1 = ea, sa, eb, sb
            break
    d0 = s0 - E_TRUE * (e0 - 0.002)
    d1 = s1 - E_TRUE * (e1 - 0.002)
    return s0 + (s1 - s0) * d0 / (d0 - d1)


@pytest.fixture
def plastic_flow(tmp_path: Path) -> Flow:
    """Flow whose ramp passes through yield."""
    return _run(tmp_path, plastic=True)


def _curve(flow: Flow) -> tuple[list[CurvePoint], Measured]:
    """Rebuild the stress-strain curve and fitted E from the flow's raw events via public API."""
    cal = [e for e in flow.events if isinstance(e, CalPoint)]
    fit = fit_calibration([c.volts for c in cal], [c.height for c in cal]).danger_ok
    tb = [e for e in flow.events if isinstance(e, TareBlock)]
    tare_m = pool_tare([t.mean for t in tb], [t.sd for t in tb], [t.n for t in tb]).danger_ok
    spec = next(e for e in flow.events if isinstance(e, SpecimenSetup))

    def meas(v: float, u: float, unit: str) -> Measured:
        return Measured.create(v, u, unit, provenance=Provenance(source="e2e")).danger_ok

    pts = [e for e in flow.events if isinstance(e, LoadPoint)]
    curve: list[CurvePoint] = []
    for i, p in enumerate(pts):
        loaded = compute_loading(
            LoadingInputs(
                voltage=meas(p.volts, p.u_volts, "V"), tare=tare_m, slope=fit.slope,
                masses=(meas(p.mass_kg, p.u_mass_kg, "kg"),),
                hanger=meas(spec.hanger_kg, spec.u_hanger_kg, "kg"),
                diameter=meas(spec.diameter, spec.u_diameter, "m"),
            )
        ).danger_ok  # fmt: skip
        curve.append(CurvePoint(index=i, stress=loaded.stress, strain=loaded.strain))
    elastic = fit_modulus(curve, 0, len(ELASTIC_STRAINS) - 1).danger_ok
    return curve, elastic.modulus


# frob:tests python/sadi/labs/lctt/yield_.py::find_yield
# frob:tests python/sadi/labs/lctt/live.py::recompute
def test_yield_stress_recovered_from_ad3_plastic_ramp(plastic_flow: Flow) -> None:
    """Offset yield stress comes back near the analytic crossing, with a finite uncertainty."""
    res = _recompute(plastic_flow.events)
    assert "yield_stress" not in res.pending
    y = res.get("yield_stress")
    assert y is not None
    _log.info("yield %g +- %g (expected %g)", y.value, y.std_unc, _expected_yield())
    assert y.value == pytest.approx(_expected_yield(), rel=0.03)
    assert 0 < y.std_unc < 0.1 * y.value
    # Ultimate stress is the top of the curve, from the same AD3 data.
    curve, modulus = _curve(plastic_flow)
    found = find_yield(curve, modulus)
    ys = found.expect("find_yield")
    assert ys.ultimate_stress.value == pytest.approx(PLASTIC[-1][1], rel=0.03)
    assert ys.ultimate_index == len(curve) - 1


# frob:tests python/sadi/labs/lctt/live.py::recompute
def test_yield_stays_pending_for_elastic_only_run(tmp_path: Path) -> None:
    """A run that never leaves the elastic range reports yield as pending with a reason."""
    res = _recompute(_run(tmp_path, plastic=False).events)
    assert res.get("E") is not None
    assert res.get("yield_stress") is None
    assert "yield_stress" in res.pending
    assert any("yield" in n for n in res.notes)


# frob:tests python/sadi/uncertainty/uncertain.py::Uncertain.cross_check
# frob:tests python/sadi/core/results.py::with_mc
def test_monte_carlo_agrees_with_analytic_yield_uncertainty(plastic_flow: Flow) -> None:
    """MC on the real yield function agrees with RSS and fills the result's cross-check flag."""
    curve, modulus = _curve(plastic_flow)
    found = find_yield(curve, modulus)
    ys = found.expect("find_yield")
    a, b = (curve[i] for i in ys.segment)
    off = Measured.create(0.002, 0.0, "dimensionless", provenance=Provenance(source="o")).danger_ok
    args = (a.stress, a.strain, b.stress, b.strain, modulus, off)

    est = yield_stress.monte_carlo(*args, n=20000, seed=5)
    mc = est.expect("monte carlo")
    rss = ys.yield_stress
    assert mc.mean == pytest.approx(rss.value, rel=0.01)
    assert mc.std > 0
    assert mc_crosscheck(rss.std_unc, mc.std).status is McStatus.AGREES

    report = yield_stress.cross_check(*args)
    checked = report.expect("cross_check")
    assert checked.agree, checked.findings

    base = _recompute(plastic_flow.events)
    assert base.refinement == ("E", "yield_stress")
    done = with_mc(base, {"yield_stress": mc.std})
    assert done.refinement == ()
    flagged = done.get("yield_stress")
    assert flagged is not None
    assert flagged.mc is not None
    assert flagged.mc.mc_std_unc == pytest.approx(mc.std)
    assert flagged.mc.status is McStatus.AGREES
