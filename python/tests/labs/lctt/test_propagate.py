"""LCTT error propagation: GUM vs Monte Carlo, budget consistency, correlation, invalid input."""

# frob:ticket 01M72X7SDBW19CXXYQA63ECN6C

from __future__ import annotations

import math

from typani import Err

from sadi.labs.lctt.loading import STANDARD_G
from sadi.labs.lctt.propagate import (
    Hang,
    PropagateError,
    PropagationInputs,
    PropagationResult,
    propagate,
)
from sadi.uncertainty import DEFAULT_REGISTRY, CovarianceRegistry, Measured

D, L0, SLOPE, TARE = 0.0005, 0.08313, 0.002, 0.5
E_TRUE, SIGMA_Y = 70e9, 400e6


def _m(value: float, unc: float, unit: str = "1", reg: CovarianceRegistry = DEFAULT_REGISTRY):
    made = Measured.create(value, unc, unit, registry=reg)
    assert not isinstance(made, Err), made
    return made.danger_ok


def _volts(sigma: float) -> float:
    """Voltage of an elastic-plastic aluminium-like curve at stress sigma."""
    eps = sigma / E_TRUE + (0.01 * (sigma - SIGMA_Y) / 100e6 if sigma > SIGMA_Y else 0.0)
    return TARE + eps * L0 / SLOPE


def _inputs(n_hangs: int = 8, *, slope_unc: float = 2e-6, offset: float = 0.002):
    """Eight 2 kg weights hung cumulatively; E is fitted on the first three (elastic) hangs."""
    area = math.pi * D**2 / 4
    inv = tuple(_m(2.0, 0.002, "kg") for _ in range(8))
    hangs = tuple(
        Hang(
            weights=tuple(range(k)),
            voltage=_m(_volts((2.0 * k + 0.5) * STANDARD_G / area), 2e-4, "V"),
        )
        for k in range(1, n_hangs + 1)
    )
    return PropagationInputs(
        inventory=inv,
        hanger=_m(0.5, 0.001, "kg"),
        diameter=_m(D, 2e-6, "m"),
        l0=_m(L0, 1e-4, "m"),
        slope=_m(SLOPE, slope_unc, "m/V"),
        tare=_m(TARE, 2e-4, "V"),
        hangs=hangs,
        offset=offset,
        window=(0, min(2, n_hangs - 1)) if n_hangs > 1 else None,
    )


def _ok(r) -> PropagationResult:
    assert not isinstance(r, Err), r
    return r.danger_ok


# frob:tests python/sadi/labs/lctt/propagate.py::propagate
def test_gum_matches_monte_carlo() -> None:
    """Linear GUM u agrees with Monte Carlo sd for stress, strain, E and yield."""
    res = _ok(propagate(_inputs(), mc_n=40000))
    assert res.modulus is not None and res.yield_stress is not None
    quantities = [res.stress[0], res.stress[-1], res.strain[0], res.strain[-1], res.modulus]
    for q in [*quantities, res.yield_stress]:
        assert q.monte_carlo is not None
        assert math.isclose(q.std_unc, q.monte_carlo.std, rel_tol=0.05), q.name
        assert q.low95 < q.value < q.high95
    assert math.isclose(res.modulus.value, E_TRUE, rel_tol=0.01)
    assert 400e6 < res.yield_stress.value < 520e6


# frob:tests python/sadi/labs/lctt/propagate.py::propagate
def test_budget_contributions_sum_to_variance() -> None:
    """Per-input contributions sum to u^2 and the dominant input is ranked first."""
    res = _ok(propagate(_inputs()))
    assert res.modulus is not None and res.yield_stress is not None
    for q in [*res.stress, *res.strain, res.modulus, res.yield_stress]:
        total = sum(r.contribution for r in q.budget.rows)
        assert math.isclose(total, q.std_unc**2, rel_tol=1e-9), q.name
        assert q.budget.rows[0].rank == 1
    names = {r.name for r in res.stress[0].budget.rows}
    assert names == {"weight_1", "hanger_mass", "diameter"}


# frob:tests python/sadi/labs/lctt/propagate.py::propagate
def test_shared_calibration_correlation_changes_strain_u() -> None:
    """A declared slope/tare correlation enters the budget, MC and the sum rule."""
    reg = CovarianceRegistry()
    base = _inputs()
    slope = _m(SLOPE, 2e-5, "m/V", reg)
    tare = _m(TARE, 2e-3, "V", reg)
    inp = base.model_copy(update={"slope": slope, "tare": tare})
    # inventory etc. live in the default registry; only slope/tare covariance is in `reg`
    # so rebuild everything in one registry for a consistent test.
    inp = PropagationInputs(
        inventory=tuple(_m(2.0, 0.002, "kg", reg) for _ in range(8)),
        hanger=_m(0.5, 0.001, "kg", reg),
        diameter=_m(D, 2e-6, "m", reg),
        l0=_m(L0, 1e-4, "m", reg),
        slope=slope,
        tare=tare,
        hangs=tuple(
            Hang(weights=h.weights, voltage=_m(h.voltage.value, 2e-4, "V", reg)) for h in base.hangs
        ),
        window=base.window,
    )
    ind = _ok(propagate(inp, registry=reg, mc_n=40000))
    assert not isinstance(reg.set_correlation(slope.id, tare.id, -0.9), Err)
    cor = _ok(propagate(inp, registry=reg, mc_n=40000))
    # tare cancels in E but not in the absolute strain, where slope*tare share a calibration
    q_ind, q_cor = ind.strain[0], cor.strain[0]
    assert not math.isclose(q_ind.std_unc, q_cor.std_unc, rel_tol=1e-3)
    total = sum(r.contribution for r in q_cor.budget.rows)
    assert math.isclose(total, q_cor.std_unc**2, rel_tol=1e-9)
    assert q_cor.monte_carlo is not None
    assert math.isclose(q_cor.std_unc, q_cor.monte_carlo.std, rel_tol=0.05)


# frob:tests python/sadi/labs/lctt/propagate.py::propagate
def test_single_hang_and_no_crossing_notes() -> None:
    """One hang gives stress/strain only; an elastic curve gives E but no yield."""
    one = _ok(propagate(_inputs(1)))
    assert one.modulus is None and one.yield_stress is None and one.notes
    elastic = _ok(propagate(_inputs(2)))
    assert elastic.modulus is not None and elastic.yield_stress is None


# frob:tests python/sadi/labs/lctt/propagate.py::propagate
def test_invalid_inputs_give_err() -> None:
    """Empty hangs, bad weight indices and non-positive geometry are typed errors."""
    base = _inputs(2)
    cases = {
        PropagateError.NoHangs: base.model_copy(update={"hangs": ()}),
        PropagateError.BadWeightIndex: base.model_copy(
            update={"hangs": (Hang(weights=(99,), voltage=base.hangs[0].voltage),)}
        ),
        PropagateError.BadGeometry: base.model_copy(update={"l0": _m(-1.0, 0.0, "m")}),
    }
    for err, inp in cases.items():
        res = propagate(inp)
        assert isinstance(res, Err) and res.danger_err == err
    dup = base.model_copy(update={"hangs": (Hang(weights=(1, 1), voltage=base.hangs[0].voltage),)})
    assert isinstance(propagate(dup), Err)
    bad = propagate(base.model_copy(update={"window": (1, 1)}))
    assert isinstance(bad, Err) and bad.danger_err == PropagateError.BadWindow
