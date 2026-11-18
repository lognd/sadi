"""LCTT automatic error propagation: one path for planned hangs and captured data.

Inputs are the inventory weights, hanger, wire diameter, L0, LVDT calibration (slope and tare
voltage) and the per-hang voltage; outputs are stress and strain per hang, chord modulus E and the
offset yield stress, each with u, a 95% interval and a per-input budget. The formulas are the
`@uncertain` functions of `loading`, `modulus` and `yield_` (their traced plain bodies are reused),
so nothing is restated here. Inputs sharing an id or a declared covariance (for example a slope
and tare from one calibration) are correlated through the covariance registry.
"""

# frob:ticket 01M72X7SDBW19CXXYQA63ECN6C

from __future__ import annotations

import math
from collections.abc import Callable, Sequence

from pydantic import BaseModel, ConfigDict
from typani import Err, ErrorSet, Ok, Result

from sadi.labs.lctt.loading import STANDARD_G, cross_area, load_force, strain, stress
from sadi.labs.lctt.modulus import chord_modulus
from sadi.labs.lctt.yield_ import DEFAULT_OFFSET, yield_stress
from sadi.logging_setup import get_logger
from sadi.uncertainty import (
    DEFAULT_REGISTRY,
    CovarianceRegistry,
    McEstimate,
    McSampler,
    Measured,
    effective_dof,
    interval95,
)
from sadi.uncertainty.budget import Budget, build_budget
from sadi.uncertainty.numeric import gradient

_log = get_logger(__name__)

DEFAULT_MC_SEED = 20260101


class PropagateError(ErrorSet):
    """Propagation failure; the description says what to fix."""

    NoHangs = "At least one hang is required; add a hang"
    BadWeightIndex = "A hang references a weight outside the inventory or twice; fix the indices"
    BadWindow = "The modulus window must satisfy 0 <= first < last < number of hangs; adjust it"
    BadGeometry = "Diameter and L0 must be > 0; enter real values"
    Numeric = "Derivatives could not be evaluated at these inputs; check for a singularity"
    Interval = "The 95% interval failed; check the uncertainties and degrees of freedom"
    MonteCarlo = "Monte Carlo cross-check failed; check the inputs or lower the sample count"


class Hang(BaseModel):
    """One hang: indices of the inventory weights on the hanger and the LVDT voltage Measured."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    weights: tuple[int, ...]
    voltage: Measured


class PropagationInputs(BaseModel):
    """All inputs in SI (kg, m, m/V, V, 1) as Measured; hangs are predicted or captured alike."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    inventory: tuple[Measured, ...]
    hanger: Measured
    diameter: Measured
    l0: Measured
    slope: Measured
    tare: Measured
    hangs: tuple[Hang, ...]
    offset: float = DEFAULT_OFFSET
    window: tuple[int, int] | None = None  # elastic hang indices (first, last); None = all hangs


class McSummary(BaseModel):
    """Monte Carlo sd and 95% percentile interval of one output, for cross-checking the GUM u."""

    model_config = ConfigDict(frozen=True)

    n: int
    mean: float
    std: float
    low: float
    high: float


class Quantity(BaseModel):
    """One output: value, standard uncertainty, 95% interval, per-input budget, optional MC."""

    model_config = ConfigDict(frozen=True)

    name: str
    unit: str
    value: float
    std_unc: float
    dof: float
    k95: float
    low95: float
    high95: float
    budget: Budget
    monte_carlo: McSummary | None = None


class PropagationResult(BaseModel):
    """Per-hang stress and strain plus chord E and yield stress (None when not determinable)."""

    model_config = ConfigDict(frozen=True)

    stress: tuple[Quantity, ...]
    strain: tuple[Quantity, ...]
    modulus: Quantity | None
    yield_stress: Quantity | None
    notes: tuple[str, ...] = ()


_Fn = Callable[..., object]


def _plain(fn: object) -> _Fn:
    """The undecorated math body of an `@uncertain` function, so formulas are not restated."""
    return fn.__wrapped__  # type: ignore[attr-defined, no-any-return]


class _Layout:
    """Maps the flat input vector [weights, hanger, d, l0, slope, tare, volts] to model values."""

    def __init__(self, inp: PropagationInputs) -> None:
        """Record sizes and the weight indices of every hang."""
        self.n = len(inp.inventory)
        self.hangs = tuple(h.weights for h in inp.hangs)
        self.offset = inp.offset
        self.window = inp.window if inp.window is not None else (0, len(inp.hangs) - 1)
        self.names = (
            *(f"weight_{i + 1}" for i in range(self.n)),
            "hanger_mass",
            "diameter",
            "l0",
            "lvdt_slope",
            "tare_voltage",
            *(f"voltage_{i + 1}" for i in range(len(inp.hangs))),
        )
        self.args = (
            *inp.inventory,
            inp.hanger,
            inp.diameter,
            inp.l0,
            inp.slope,
            inp.tare,
            *(h.voltage for h in inp.hangs),
        )

    def point(self, x: Sequence[object], i: int) -> tuple[object, object]:
        """Stress and strain of hang i at input vector x, from the shared loading formulas."""
        n = self.n
        hanger, d, l0, slope, tare = x[n : n + 5]
        mass = sum((x[j] for j in self.hangs[i]), 0.0) + hanger  # type: ignore[operator]
        area = _plain(cross_area)(d)
        force = _plain(load_force)(mass, 0.0, STANDARD_G)
        sig = _plain(stress)(force, area)
        eps = _plain(strain)(slope, x[n + 5 + i], tare, l0)
        return sig, eps

    def modulus(self, x: Sequence[object]) -> object:
        """Chord E between the window's first and last hang."""
        s0, e0 = self.point(x, self.window[0])
        s1, e1 = self.point(x, self.window[1])
        return _plain(chord_modulus)(s0, s1, e0, e1)

    def yield_at(self, x: Sequence[object], segment: tuple[int, int]) -> object:
        """Offset yield stress on the bracketing hang segment, with E the chord modulus."""
        s0, e0 = self.point(x, segment[0])
        s1, e1 = self.point(x, segment[1])
        return _plain(yield_stress)(s0, e0, s1, e1, self.modulus(x), self.offset)


def _validate(inp: PropagationInputs) -> Result[None, PropagateError]:
    """Reject empty hang lists, bad weight indices and non-positive geometry."""
    if not inp.hangs:
        return Err(PropagateError.NoHangs)
    n = len(inp.inventory)
    for h in inp.hangs:
        if len(set(h.weights)) != len(h.weights) or any(not 0 <= j < n for j in h.weights):
            _log.warning("propagate: bad weight indices %s for %d weights", h.weights, n)
            return Err(PropagateError.BadWeightIndex)
    if inp.window is not None and not 0 <= inp.window[0] < inp.window[1] < len(inp.hangs):
        return Err(PropagateError.BadWindow)
    if not (inp.diameter.value > 0 and inp.l0.value > 0):
        return Err(PropagateError.BadGeometry)
    return Ok(None)


def _quantity(
    name: str,
    unit: str,
    fn: _Fn,
    lay: _Layout,
    registry: CovarianceRegistry,
    mc_n: int | None,
    seed: int,
) -> Result[Quantity, PropagateError]:
    """Propagate one scalar output: gradient, budget, dof, 95% interval and optional MC."""
    grad = gradient(fn, [a.value for a in lay.args])
    if isinstance(grad, Err):
        _log.warning("propagate %s: gradient failed: %s", name, grad.danger_err)
        return Err(PropagateError.Numeric)
    g = grad.danger_ok
    used = [i for i, c in enumerate(g.gradient) if c != 0.0]
    budget = build_budget(
        [lay.names[i] for i in used],
        [lay.args[i] for i in used],
        [g.gradient[i] for i in used],
        registry,
    )
    dof: Result[float, object] = (
        effective_dof([(abs(g.gradient[i]) * lay.args[i].std_unc, lay.args[i].dof) for i in used])
        if used
        else Ok(math.inf)
    )
    iv = dof.and_then(lambda d: interval95(g.value, budget.total_std_unc, d))
    if isinstance(dof, Err) or isinstance(iv, Err):
        _log.warning("propagate %s: interval failed", name)
        return Err(PropagateError.Interval)
    d_eff = dof.danger_ok
    low, high = iv.danger_ok
    k = (high - g.value) / budget.total_std_unc if budget.total_std_unc > 0 else 0.0
    mc = None
    if mc_n is not None:
        mc = _mc(fn, lay, registry, mc_n, seed)
        if isinstance(mc, Err):
            return Err(mc.danger_err)
        mc = mc.danger_ok
    _log.info("propagate %s = %g +/- %g %s", name, g.value, budget.total_std_unc, unit)
    return Ok(
        Quantity(
            name=name,
            unit=unit,
            value=g.value,
            std_unc=budget.total_std_unc,
            dof=d_eff,
            k95=k,
            low95=low,
            high95=high,
            budget=budget,
            monte_carlo=mc,
        )
    )


def _mc(
    fn: _Fn, lay: _Layout, registry: CovarianceRegistry, n: int, seed: int
) -> Result[McSummary, PropagateError]:
    """Monte Carlo of `fn` over the full input covariance."""
    sampler = McSampler.from_measured(fn, lay.args, registry, seed=seed)
    est: Result[McEstimate, object] = (
        sampler.and_then(lambda s: s.run_to(n)) if isinstance(sampler, Ok) else sampler
    )
    if isinstance(est, Err):
        _log.warning("propagate: monte carlo failed: %s", est.danger_err)
        return Err(PropagateError.MonteCarlo)
    e = est.danger_ok
    return Ok(McSummary(n=e.n, mean=e.mean, std=e.std, low=e.low, high=e.high))


def propagate(
    inp: PropagationInputs,
    *,
    registry: CovarianceRegistry = DEFAULT_REGISTRY,
    mc_n: int | None = None,
    seed: int = DEFAULT_MC_SEED,
) -> Result[PropagationResult, PropagateError]:
    """Propagate input uncertainty to stress, strain, E and yield per the GUM; `mc_n` adds MC."""
    ok = _validate(inp)
    if isinstance(ok, Err):
        return Err(ok.danger_err)
    lay = _Layout(inp)
    notes: list[str] = []
    stresses: list[Quantity] = []
    strains: list[Quantity] = []
    for i in range(len(lay.hangs)):
        for out, name, unit, which in (
            (stresses, f"stress_{i + 1}", "Pa", 0),
            (strains, f"strain_{i + 1}", "1", 1),
        ):

            def fn(*x: object, _i: int = i, _w: int = which) -> object:
                return lay.point(x, _i)[_w]

            q = _quantity(name, unit, fn, lay, registry, mc_n, seed)
            if isinstance(q, Err):
                return Err(q.danger_err)
            out.append(q.danger_ok)
    modulus: Quantity | None = None
    yld: Quantity | None = None
    if len(lay.hangs) < 2:
        notes.append("E and yield need at least two hangs")
    else:

        def mfn(*x: object) -> object:
            return lay.modulus(x)

        m = _quantity("E", "Pa", mfn, lay, registry, mc_n, seed)
        if isinstance(m, Err):
            return Err(m.danger_err)
        modulus = m.danger_ok
        seg = _crossing(stresses, strains, modulus.value, inp.offset)
        if seg is None:
            notes.append("curve does not cross the offset line; no yield")
        else:

            def yfn(*x: object) -> object:
                return lay.yield_at(x, seg)

            y = _quantity("yield_stress", "Pa", yfn, lay, registry, mc_n, seed)
            if isinstance(y, Err):
                return Err(y.danger_err)
            yld = y.danger_ok
    for n in notes:
        _log.info("propagate: %s", n)
    return Ok(
        PropagationResult(
            stress=tuple(stresses),
            strain=tuple(strains),
            modulus=modulus,
            yield_stress=yld,
            notes=tuple(notes),
        )
    )


def _crossing(
    stresses: Sequence[Quantity], strains: Sequence[Quantity], e: float, offset: float
) -> tuple[int, int] | None:
    """First hang segment where the curve crosses sigma = E (eps - offset), as in find_yield."""

    def gap(i: int) -> float:
        return stresses[i].value - e * (strains[i].value - offset)

    for i in range(len(stresses) - 1):
        if gap(i) > 0 >= gap(i + 1):
            return (i, i + 1)
    return None
