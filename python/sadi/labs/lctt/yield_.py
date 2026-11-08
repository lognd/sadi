"""LCTT 0.2 % offset yield stress and ultimate stress, with uncertainty."""

# frob:ticket 01M6W7R3BBDEXG9CPYWTQ7ZKZW

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel
from typani import Err, ErrorSet, Ok, Result

from sadi.labs.lctt.modulus import CurvePoint
from sadi.logging_setup import get_logger
from sadi.uncertainty import Measured, Provenance, uncertain

_log = get_logger(__name__)

DEFAULT_OFFSET = 0.002


class YieldError(ErrorSet):
    """Yield computation failure; the description says what to fix."""

    TooFewPoints = "Need at least two points to find a yield; capture more"
    NoCrossing = "The curve never crosses the offset line; load further or check the E window"
    Propagation = "Uncertainty propagation failed; check units and inputs"


class YieldResult(BaseModel):
    """Offset yield stress/strain (Measured), the bracketing segment, and ultimate stress."""

    model_config = {"frozen": True, "arbitrary_types_allowed": True}

    yield_stress: Measured
    yield_strain: Measured
    segment: tuple[int, int]
    ultimate_stress: Measured
    ultimate_index: int


@uncertain
def yield_stress(s0, e0, s1, e1, modulus, offset):  # type: ignore[no-untyped-def]  # noqa: ANN001, ANN201
    """Stress where segment (e0,s0)-(e1,s1) meets sigma = E (eps - offset)."""
    d0 = s0 - modulus * (e0 - offset)
    d1 = s1 - modulus * (e1 - offset)
    return s0 + (s1 - s0) * d0 / (d0 - d1)


@uncertain
def yield_strain(s0, e0, s1, e1, modulus, offset):  # type: ignore[no-untyped-def]  # noqa: ANN001, ANN201
    """Strain where segment (e0,s0)-(e1,s1) meets sigma = E (eps - offset)."""
    d0 = s0 - modulus * (e0 - offset)
    d1 = s1 - modulus * (e1 - offset)
    return e0 + (e1 - e0) * d0 / (d0 - d1)


def find_yield(
    points: Sequence[CurvePoint], modulus: Measured, offset: float = DEFAULT_OFFSET
) -> Result[YieldResult, YieldError]:
    """Intersect the stress-strain polyline with the offset line of slope E; add ultimate."""
    if len(points) < 2:
        return Err(YieldError.TooFewPoints)
    off = Measured.create(offset, 0.0, "dimensionless", provenance=Provenance(source="offset"))
    if isinstance(off, Err):
        return Err(YieldError.Propagation)
    e_val = modulus.value

    def gap(p: CurvePoint) -> float:
        return p.stress.value - e_val * (p.strain.value - offset)

    for a, b in zip(points, points[1:], strict=False):
        if gap(a) > 0 >= gap(b):
            args = (a.stress, a.strain, b.stress, b.strain, modulus, off.danger_ok)
            sy, ey = yield_stress(*args), yield_strain(*args)
            for r in (sy, ey):
                if isinstance(r, Err):
                    _log.warning("find_yield: propagation failed: %s", r.danger_err)
                    return Err(YieldError.Propagation)
            top = max(points, key=lambda p: p.stress.value)
            _log.info(
                "find_yield: sigma_y=%g between points %d,%d", sy.danger_ok.value, a.index, b.index
            )
            return Ok(
                YieldResult(
                    yield_stress=sy.danger_ok,
                    yield_strain=ey.danger_ok,
                    segment=(a.index, b.index),
                    ultimate_stress=top.stress,
                    ultimate_index=top.index,
                )
            )
    _log.warning("find_yield: no crossing at offset %g", offset)
    return Err(YieldError.NoCrossing)
