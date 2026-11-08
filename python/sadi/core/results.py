"""Live result models: one value with 95 % interval and readout, and the full ResultSet."""

# frob:ticket 01M6W7R3J00J2HQ7XPW19WDD6Q

from __future__ import annotations

import math
from enum import StrEnum

from pydantic import BaseModel, ConfigDict
from typani import Err, ErrorSet, Ok, Result

from sadi.core.formatting import FormatConfig, format_result, plain_language_confidence
from sadi.logging_setup import get_logger
from sadi.uncertainty import t95

_log = get_logger(__name__)

#: Default relative-uncertainty target (fraction) for the plain-language readout.
DEFAULT_TARGET = 0.05

#: Relative RSS-vs-MC standard-uncertainty disagreement above which the flag is raised.
MC_AGREE_TOL = 0.10


class ResultsError(ErrorSet):
    """Result construction failure; the description says what to fix."""

    BadValue = "Result value and uncertainty must be finite with uncertainty >= 0"
    BadDof = "Degrees of freedom must be positive"


class McStatus(StrEnum):
    """State of the RSS vs Monte Carlo cross-check."""

    PENDING = "pending"
    AGREES = "agrees"
    DISAGREES = "disagrees"


class McCrossCheck(BaseModel):
    """RSS vs MC flag; MC runs as a job (J3), so a fresh result starts PENDING."""

    model_config = ConfigDict(frozen=True)

    status: McStatus = McStatus.PENDING
    mc_std_unc: float | None = None


class ResultValue(BaseModel):
    """One reported quantity: value, standard and 95 % uncertainty, interval, readouts."""

    model_config = ConfigDict(frozen=True)

    name: str
    value: float
    std_unc: float
    u95: float
    low95: float
    high95: float
    unit: str
    dof: float | None = None
    display: str
    confidence: str
    mc: McCrossCheck = McCrossCheck()


class ResultSet(BaseModel):
    """Everything the live panel shows after one recompute; analytic RSS only (instant)."""

    model_config = ConfigDict(frozen=True)

    n_points: int = 0
    values: tuple[ResultValue, ...] = ()
    pending: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    refinement: tuple[str, ...] = ()

    def get(self, name: str) -> ResultValue | None:
        """Return the named result, or None when it is not computable yet."""
        return next((v for v in self.values if v.name == name), None)


def make_result(  # noqa: PLR0913
    name: str,
    value: float,
    std_unc: float,
    unit: str,
    *,
    dof: float | None = None,
    target: float = DEFAULT_TARGET,
    config: FormatConfig | None = None,
) -> Result[ResultValue, ResultsError]:
    """Build a ResultValue with t95 interval, class-rule display and confidence string."""
    if not (math.isfinite(value) and math.isfinite(std_unc) and std_unc >= 0):
        _log.warning("make_result %s: bad value=%r u=%r", name, value, std_unc)
        return Err(ResultsError.BadValue)
    k = t95(dof)
    if isinstance(k, Err):
        return Err(ResultsError.BadDof)
    u95 = k.danger_ok * std_unc
    cfg = config or FormatConfig()
    shown = format_result(value, u95, unit, cfg)
    display = shown.danger_ok if isinstance(shown, Ok) else f"{value:g} {unit}"
    conf = plain_language_confidence(value, u95, target, name, cfg)
    if isinstance(conf, Ok):
        confidence = conf.danger_ok
    else:
        _log.debug("make_result %s: no relative readout (%s)", name, conf.danger_err)
        confidence = f"{name}: relative uncertainty is not defined for this value"
    return Ok(
        ResultValue(
            name=name,
            value=value,
            std_unc=std_unc,
            u95=u95,
            low95=value - u95,
            high95=value + u95,
            unit=unit,
            dof=dof,
            display=display,
            confidence=confidence,
        )
    )


def mc_crosscheck(rss_std_unc: float, mc_std_unc: float, tol: float = MC_AGREE_TOL) -> McCrossCheck:
    """Compare analytic RSS to a Monte Carlo standard uncertainty; flag when they differ > tol."""
    scale = max(abs(rss_std_unc), abs(mc_std_unc))
    agree = scale == 0 or abs(rss_std_unc - mc_std_unc) / scale <= tol
    status = McStatus.AGREES if agree else McStatus.DISAGREES
    _log.info("mc_crosscheck rss=%g mc=%g -> %s", rss_std_unc, mc_std_unc, status)
    return McCrossCheck(status=status, mc_std_unc=mc_std_unc)


def with_mc(result: ResultSet, mc_std_unc: dict[str, float]) -> ResultSet:
    """Return `result` with MC cross-check flags filled from a finished job; pure."""
    vals = tuple(
        v.model_copy(update={"mc": mc_crosscheck(v.std_unc, mc_std_unc[v.name])})
        if v.name in mc_std_unc
        else v
        for v in result.values
    )
    return result.model_copy(update={"values": vals, "refinement": ()})
