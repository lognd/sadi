"""Weight-subset planner: which inventory weights to hang, in order, with uncertainty (advisory)."""

# frob:ticket 01M72X7S8DA8X3Q95HRYNKT2ED

from __future__ import annotations

import itertools
import math

from typani import Err, ErrorSet, Ok, Result

from sadi.design.models import (
    Candidate,
    DesignPhase,
    GpState,
    Hang,
    Obs,
    PlanRequest,
    SelectorConfig,
    Weight,
    WeightPlan,
)
from sadi.design.selector import select_next
from sadi.labs.lctt.loading import STANDARD_G
from sadi.labs.lctt.saturation import DEFAULT_SATURATION_V
from sadi.logging_setup import get_logger
from sadi.synthetic.specimen import OFFSET_STRAIN

__all__ = ["MAX_WEIGHTS", "PlanError", "plan"]

_log = get_logger(__name__)

#: Hard limit on the inventory size (2^12 subsets is still instant); the lab has 8.
MAX_WEIGHTS = 12
#: Coverage factor applied to the standard uncertainties of the geometry in the E half-width.
_K_GEOM = 2.0


class PlanError(ErrorSet):
    """Why no plan could be made; the description says what to fix."""

    NoWeights = "The inventory has no weights to plan with"
    TooManyWeights = "The inventory has more than 12 weights; enter at most 12"
    DuplicateIds = "Two weights share an id; give every weight its own id"
    NoUsableHang = "No combination of weights stays under saturation and wire capacity"
    NonFinite = "A weight, geometry or calibration value is not a finite number"
    SelectorFailed = "The design model could not rank the loads"


class _Load:
    """One achievable, deduplicated hang (cumulative load on the wire)."""

    __slots__ = ("ids", "mass", "u_mass")

    def __init__(self, ids: tuple[str, ...], mass: float, u_mass: float) -> None:
        self.ids, self.mass, self.u_mass = ids, mass, u_mass


def _subsets(weights: tuple[Weight, ...], res: float) -> list[_Load]:
    """Enumerate non-empty subset sums, deduped by total mass keeping the lowest ids."""
    ordered = sorted(weights, key=lambda w: w.weight_id)
    best: dict[int, _Load] = {}
    for k in range(1, len(ordered) + 1):
        for combo in itertools.combinations(ordered, k):
            mass = math.fsum(w.mass_kg for w in combo)
            ids = tuple(w.weight_id for w in combo)
            key = round(mass / res)
            cur = best.get(key)
            if cur is None or ids < cur.ids:
                best[key] = _Load(ids, mass, math.sqrt(math.fsum(w.u_mass_kg**2 for w in combo)))
    return sorted(best.values(), key=lambda ld: (ld.mass, ld.ids))


def _finite(req: PlanRequest) -> bool:
    vals = [req.diameter_m, req.u_diameter_m, req.length_m, req.u_length_m, req.cal_slope_v_per_m]
    vals += [req.cal_offset_v]
    vals += [x for w in req.weights for x in (w.mass_kg, w.u_mass_kg)]
    vals += [x for c in req.captured for x in (c.mass_kg, c.volts, c.u_volts)]
    return all(math.isfinite(v) for v in vals)


def _volts_per_kg(req: PlanRequest) -> float:
    """Elastic response slope in V per kg from the modulus prior."""
    area = math.pi * req.diameter_m**2 / 4.0
    return req.cal_slope_v_per_m * STANDARD_G * req.length_m / (area * req.config.copper.e_pa)


def _predict(req: PlanRequest, mass: float, phase: DesignPhase) -> float:
    """Predicted LVDT volts at `mass`: linear in the elastic phase, copper curve in yield."""
    cfg = req.config
    area = math.pi * req.diameter_m**2 / 4.0
    if phase is DesignPhase.YIELD:
        stress = mass * STANDARD_G / area
        dl = cfg.copper.strain(stress, stress) * req.length_m
        return req.cal_offset_v + req.cal_slope_v_per_m * dl
    return req.cal_offset_v + _volts_per_kg(req) * mass


def _phase(req: PlanRequest) -> DesignPhase:
    """Yield once enough points exist and the captured load has reached the plastic onset."""
    cfg = req.config
    if len(req.captured) < cfg.selector.n_min_yield:
        return DesignPhase.ELASTIC
    area = math.pi * req.diameter_m**2 / 4.0
    top = max(c.mass_kg for c in req.captured)
    return (
        DesignPhase.YIELD if top * STANDARD_G / area >= cfg.copper.onset_pa else DesignPhase.ELASTIC
    )


def _selector_cfg(req: PlanRequest, phase: DesignPhase) -> SelectorConfig:
    cfg = req.config.selector
    if phase is DesignPhase.YIELD and cfg.offset_response is None:
        off = abs(req.cal_slope_v_per_m) * OFFSET_STRAIN * req.length_m
        return cfg.model_copy(update={"offset_response": off})
    return cfg


def _reason(order: int, phase: DesignPhase, gain: float, why: str) -> str:
    kind = "yield load" if phase is DesignPhase.YIELD else "modulus"
    base = f"Hang #{order}: {why}"
    if gain > 0:
        return f"{base} Expected to tighten the {kind} interval by {gain:.3g}."
    return base


def _usable(
    req: PlanRequest, loads: list[_Load], phase: DesignPhase, sat_v: float
) -> tuple[list[_Load], int, int]:
    """Drop loads that saturate the LVDT or exceed the wire capacity; return counts dropped."""
    cap_n = req.config.capacity_fraction * req.config.copper.ultimate_pa
    cap_n *= math.pi * req.diameter_m**2 / 4.0
    keep: list[_Load] = []
    n_sat = n_cap = 0
    for ld in loads:
        if ld.mass * STANDARD_G > cap_n:
            n_cap += 1
        elif abs(_predict(req, ld.mass, phase)) > sat_v:
            n_sat += 1
        else:
            keep.append(ld)
    return keep, n_sat, n_cap


def _halves(req: PlanRequest, phase: DesignPhase, obs: list[Obs], first: int) -> list[tuple]:
    """Post-hang half-widths: one (slope_half, value) per prefix of the simulated points."""
    out: list[tuple] = []
    tgt, cfg = req.config.target, _selector_cfg(req, phase)
    for k in range(first, len(obs) + 1):
        adv = select_next(phase, obs[:k], [Candidate(candidate_id="x", x=obs[-1].x)], tgt, cfg)
        cur = adv.unwrap().indicator.current if isinstance(adv, Ok) else None
        out.append((cur.half_width, cur.value) if cur else (None, None))
    return out


def plan(req: PlanRequest) -> Result[WeightPlan, PlanError]:
    """Choose an ordered sequence of hangs from the inventory (deterministic, advisory)."""
    ids = [w.weight_id for w in req.weights]
    if not ids:
        return Err(PlanError.NoWeights)
    if len(ids) > MAX_WEIGHTS:
        _log.warning("plan refused: %d weights > %d", len(ids), MAX_WEIGHTS)
        return Err(PlanError.TooManyWeights)
    if len(set(ids)) != len(ids):
        return Err(PlanError.DuplicateIds)
    if not _finite(req):
        return Err(PlanError.NonFinite)

    cfg = req.config
    phase = _phase(req)
    sat_v = req.saturation_v if req.saturation_v is not None else DEFAULT_SATURATION_V
    loads = _subsets(req.weights, cfg.mass_resolution_kg)
    floor = max((c.mass_kg for c in req.captured), default=0.0)
    usable, n_sat, n_cap = _usable(req, loads, phase, sat_v)
    usable = [ld for ld in usable if ld.mass > floor + cfg.mass_resolution_kg]
    _log.info(
        "plan phase=%s weights=%d loads=%d usable=%d sat=%d cap=%d",
        phase.value,
        len(ids),
        len(loads),
        len(usable),
        n_sat,
        n_cap,
    )
    if not usable:
        return Err(PlanError.NoUsableHang)

    by_id = {"|".join(ld.ids): ld for ld in usable}
    obs = [Obs(x=c.mass_kg, y=c.volts, u=c.u_volts) for c in req.captured]
    n_cap_pts = len(obs)
    sel = _selector_cfg(req, phase)
    chosen: list[tuple[_Load, float, str]] = []
    remaining = list(usable)
    limit = cfg.max_hangs or len(usable)
    while remaining and len(chosen) < limit:
        cands = [Candidate(candidate_id="|".join(ld.ids), x=ld.mass) for ld in remaining]
        got = select_next(phase, obs, cands, cfg.target, sel, unit="kg")
        if isinstance(got, Err):
            _log.error("selector failed: %s", got.unwrap_err())
            return Err(PlanError.SelectorFailed)
        adv = got.unwrap()
        if chosen and adv.indicator.state is GpState.ENOUGH:
            break
        sug = adv.suggestion
        assert sug is not None  # noqa: S101 - select_next always suggests when candidates exist
        ld = by_id[sug.candidate_id]
        v = _predict(req, ld.mass, phase)
        obs.append(Obs(x=ld.mass, y=v, u=abs(_volts_per_kg(req)) * ld.u_mass))
        chosen.append((ld, sug.expected_gain, sug.why))
        remaining = [r for r in remaining if r.mass > ld.mass + cfg.mass_resolution_kg]

    halves = _halves(req, phase, obs, n_cap_pts + 1)
    hangs = tuple(
        _hang(req, phase, i + 1, ld, gain, why, hv)
        for i, ((ld, gain, why), hv) in enumerate(zip(chosen, halves, strict=True))
    )
    return Ok(
        WeightPlan(
            phase=phase,
            hangs=hangs,
            n_inventory=len(ids),
            n_achievable=len(loads),
            n_usable=len(usable),
            dropped_saturation=n_sat,
            dropped_capacity=n_cap,
        )
    )


def _hang(
    req: PlanRequest,
    phase: DesignPhase,
    order: int,
    ld: _Load,
    gain: float,
    why: str,
    hv: tuple,
) -> Hang:
    """Build one reported hang, propagating slope uncertainty to E with the geometry."""
    half, value = hv
    slope_half = e_half = yield_half = None
    if half is not None and phase is DesignPhase.YIELD:
        yield_half = half
    elif half is not None and value:
        slope_half = half
        rel2 = (half / abs(value)) ** 2
        rel2 += (_K_GEOM * 2.0 * req.u_diameter_m / req.diameter_m) ** 2
        rel2 += (_K_GEOM * req.u_length_m / req.length_m) ** 2
        e_half = req.config.copper.e_pa * math.sqrt(rel2)
    return Hang(
        order=order,
        weight_ids=ld.ids,
        total_mass_kg=ld.mass,
        u_mass_kg=ld.u_mass,
        tension_n=ld.mass * STANDARD_G,
        predicted_volts=_predict(req, ld.mass, phase),
        u_predicted_volts=abs(_volts_per_kg(req)) * ld.u_mass,
        expected_gain=gain,
        slope_half_width_v_per_kg=slope_half,
        e_half_width_pa=e_half,
        yield_half_width_kg=yield_half,
        reason=_reason(order, phase, gain, why),
    )
