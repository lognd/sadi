"""Gauge-height planner: which heights to calibrate with, and their uncertainty."""

# frob:ticket 01M7305JYQ6AZA2Z92Y5QQ54BF

from __future__ import annotations

import itertools
import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from typani import Err, ErrorSet, Ok, Result

from sadi.design.models import Candidate, DesignPhase, GpState, Obs, SelectorConfig, TargetSpec
from sadi.design.selector import select_next
from sadi.labs.lctt.saturation import DEFAULT_SATURATION_V
from sadi.logging_setup import get_logger

__all__ = ["Height", "HeightPlan", "HeightPlanError", "HeightStep", "parse_heights", "plan_heights", "stack_heights"]

_log = get_logger(__name__)

#: Hard limit on the height inventory, matching the weight inventory.
MAX_HEIGHTS = 12
#: Height uncertainty (m) used for any height entered without one: 0.1 mm.
DEFAULT_U_HEIGHT_M = 1e-4
#: Most heights stacked into one gauge height (h1+h2+h3); keeps the candidate list small.
MAX_STACK = 3
_TARGET = TargetSpec(half_width=0.05)
_CONFIG = SelectorConfig()


class HeightPlanError(ErrorSet):
    """Why no height plan could be made; the description says what to fix."""

    TooFew = "Need at least 2 distinct usable heights to calibrate the LVDT"
    TooMany = "The inventory has more than 12 heights; enter at most 12"
    NonFinite = "A height, uncertainty or nominal calibration value is not a finite number"
    ZeroSlope = "The nominal LVDT slope is zero, so heights cannot be told apart"
    SelectorFailed = "The design model could not rank the heights"


class Height(BaseModel):
    """One available gauge height (m) with its own uncertainty; duplicates are distinct ids."""

    model_config = ConfigDict(frozen=True)

    height_id: str
    height_m: float
    u_height_m: float = Field(default=0.0, ge=0)


class HeightStep(BaseModel):
    """One chosen height: use order, its uncertainty and the running slope/intercept uncertainty."""

    model_config = ConfigDict(frozen=True)

    order: int
    height_id: str
    height_m: float
    u_height_m: float
    predicted_volts: float | None
    se_slope_v_per_m: float | None
    se_offset_v: float | None
    rel_se_slope: float | None = None
    expected_gain: float
    reason: str


class HeightPlan(BaseModel):
    """Ordered heights to use, with the final propagated calibration uncertainty."""

    model_config = ConfigDict(frozen=True)

    steps: tuple[HeightStep, ...]
    n_inventory: int
    n_usable: int
    dropped_saturation: int
    se_slope_v_per_m: float | None
    se_offset_v: float | None
    rel_se_slope: float | None = None
    slope_known: bool = True
    basis: Literal["design"] = "design"


def parse_heights(text: str, default_u_m: float = DEFAULT_U_HEIGHT_M) -> Result[list[Height], str]:
    """Parse 'h:u,h:u' (metres; u optional, default_u_m when blank) into h1, h2, ...; duplicates stay distinct."""
    out: list[Height] = []
    parts = [t.strip() for t in text.replace(";", ",").replace("\n", ",").split(",")]
    for i, part in enumerate(p for p in parts if p):
        try:
            f = part.split(":")
            if len(f) not in (1, 2):
                raise ValueError("expected height or height:uncertainty")
            u = float(f[1]) if len(f) == 2 and f[1].strip() else default_u_m
            out.append(Height(height_id=f"h{i + 1}", height_m=float(f[0]), u_height_m=u))
        except (ValueError, ValidationError) as exc:
            _log.warning("bad height %r: %s", part, exc)
            return Err(
                f"Could not read height {part!r} (use height_m or height_m:u_height_m): {exc}"
            )
    return Ok(out)


def stack_heights(heights: list[Height], max_stack: int = MAX_STACK) -> list[Height]:
    """All stackings of up to max_stack heights as 'h1+h2' candidates; u adds in quadrature, equal totals keep the lowest ids."""
    seen: dict[float, Height] = {}
    for k in range(1, min(max_stack, len(heights)) + 1):
        for combo in itertools.combinations(heights, k):
            total = math.fsum(h.height_m for h in combo)
            key = round(total, 9)
            if key in seen:
                continue
            seen[key] = Height(
                height_id="+".join(h.height_id for h in combo),
                height_m=total,
                u_height_m=math.sqrt(math.fsum(h.u_height_m**2 for h in combo)),
            )
    _log.debug("stacked %d heights into %d candidates", len(heights), len(seen))
    return sorted(seen.values(), key=lambda h: h.height_m)


def _se(chosen: list[Height], slope: float) -> tuple[float | None, float | None]:
    """Propagate per-height u into slope/intercept se: weighted LS with sigma_v = |slope| u_h.

    Needs >= 2 distinct heights; zero uncertainties give zero se (exact heights).
    """
    if len({h.height_m for h in chosen}) < 2:
        return None, None
    if any(h.u_height_m <= 0 for h in chosen):
        return (0.0, 0.0) if all(h.u_height_m <= 0 for h in chosen) else (None, None)
    w = [1.0 / (slope * h.u_height_m) ** 2 for h in chosen]
    sw = math.fsum(w)
    xb = math.fsum(wi * h.height_m for wi, h in zip(w, chosen, strict=True)) / sw
    sxx = math.fsum(wi * (h.height_m - xb) ** 2 for wi, h in zip(w, chosen, strict=True))
    return math.sqrt(1.0 / sxx), math.sqrt(1.0 / sw + xb**2 / sxx)


def plan_heights(  # noqa: PLR0913
    heights: list[Height],
    *,
    nominal_slope_v_per_m: float | None = None,
    nominal_offset_v: float = 0.0,
    saturation_v: float | None = None,
    min_m: float | None = None,
    max_m: float | None = None,
    n_points: int | None = None,
    target: TargetSpec = _TARGET,
    config: SelectorConfig = _CONFIG,
) -> Result[HeightPlan, HeightPlanError]:
    """Pick the ordered heights via the GP selector; without a slope, plan in height space only.

    With no nominal slope there is no volts prediction and no saturation filter; the slope
    uncertainty is then reported relative to the (unknown) slope.
    """
    known = nominal_slope_v_per_m is not None
    slope = nominal_slope_v_per_m if nominal_slope_v_per_m is not None else 1.0
    if len(heights) > MAX_HEIGHTS:
        return Err(HeightPlanError.TooMany)
    if not all(math.isfinite(v) for h in heights for v in (h.height_m, h.u_height_m)) or not all(
        math.isfinite(v) for v in (slope, nominal_offset_v)
    ):
        return Err(HeightPlanError.NonFinite)
    if slope == 0:
        return Err(HeightPlanError.ZeroSlope)
    sat = saturation_v if saturation_v is not None else DEFAULT_SATURATION_V

    def volts(h: Height) -> float:
        return nominal_offset_v + slope * h.height_m

    stacks = [
        h for h in stack_heights(heights)
        if (min_m is None or h.height_m >= min_m) and (max_m is None or h.height_m <= max_m)
    ]
    usable = [h for h in stacks if abs(volts(h)) <= sat] if known else stacks
    n_sat = len(stacks) - len(usable)
    if len({h.height_m for h in heights}) < 2 or len({h.height_m for h in usable}) < 2:
        _log.warning(
            "height plan refused: %d distinct usable of %d (sat dropped %d)",
            len({h.height_m for h in usable}),
            len(heights),
            n_sat,
        )
        return Err(HeightPlanError.TooFew)

    by_id = {h.height_id: h for h in usable}
    if len(by_id) != len(usable):  # same id twice: keep them distinct by position
        by_id = {f"{h.height_id}#{i}": h for i, h in enumerate(usable)}
    remaining = list(by_id)
    obs: list[Obs] = []
    chosen: list[tuple[str, float, str]] = []
    while remaining:
        cands = [
            Candidate(candidate_id=k, x=by_id[k].height_m, u_x=by_id[k].u_height_m)
            for k in remaining
        ]
        got = select_next(DesignPhase.ELASTIC, obs, cands, target, config, unit="m")
        if isinstance(got, Err):
            _log.error("height selector failed: %s", got.unwrap_err())
            return Err(HeightPlanError.SelectorFailed)
        adv = got.unwrap()
        # Need two distinct heights before stopping so a slope exists.
        if n_points is not None and len(chosen) >= n_points:
            break
        if n_points is None and len({o.x for o in obs}) >= 2 and adv.indicator.state is GpState.ENOUGH:
            break
        sug = adv.suggestion
        if sug is None:  # range exhausted: no remaining height is beyond the last one used
            break
        h = by_id[sug.candidate_id]
        obs.append(Obs(x=h.height_m, y=volts(h), u=abs(slope) * h.u_height_m))
        chosen.append((sug.candidate_id, sug.expected_gain, sug.why))
        remaining.remove(sug.candidate_id)

    steps: list[HeightStep] = []
    for i, (cid, gain, why) in enumerate(chosen):
        h = by_id[cid]
        ses, seo = _se([by_id[c] for c, _, _ in chosen[: i + 1]], slope)
        steps.append(
            HeightStep(
                order=i + 1,
                height_id=h.height_id,
                height_m=h.height_m,
                u_height_m=h.u_height_m,
                predicted_volts=volts(h) if known else None,
                se_slope_v_per_m=ses if known else None,
                se_offset_v=seo if known else None,
                rel_se_slope=None if known or ses is None else ses / abs(slope),
                expected_gain=gain,
                reason=f"Height #{i + 1}: {why}",
            )
        )
    last = steps[-1]
    _log.info(
        "height plan: %d of %d heights chosen, se_slope=%s",
        len(steps),
        len(heights),
        last.se_slope_v_per_m,
    )
    return Ok(
        HeightPlan(
            steps=tuple(steps),
            n_inventory=len(heights),
            n_usable=len(usable),
            dropped_saturation=n_sat,
            se_slope_v_per_m=last.se_slope_v_per_m,
            se_offset_v=last.se_offset_v,
            rel_se_slope=last.rel_se_slope,
            slope_known=known,
        )
    )
