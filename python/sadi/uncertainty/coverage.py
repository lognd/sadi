"""Coverage utilities: t95, 95% interval, relative uncertainty, Welch-Satterthwaite dof."""

# frob:ticket 01M6W7R155JD0XGVXHDSP19B1H

from __future__ import annotations

import math
from collections.abc import Sequence

from scipy import stats
from typani import Err, Ok, Result

from sadi.logging_setup import get_logger
from sadi.uncertainty.errors import UncertaintyError

_log = get_logger(__name__)

NORMAL_K95 = 1.959963984540054


def t95(dof: float | None) -> Result[float, UncertaintyError]:
    """Return the two-sided 95% Student-t factor; None or inf dof gives the normal 1.96."""
    if dof is None or math.isinf(dof):
        return Ok(NORMAL_K95)
    if math.isnan(dof) or dof <= 0:
        _log.warning("t95 rejected dof=%r", dof)
        return Err(UncertaintyError.InvalidDof)
    return Ok(float(stats.t.ppf(0.975, dof)))


def interval95(
    value: float, std_unc: float, dof: float | None = None
) -> Result[tuple[float, float], UncertaintyError]:
    """Return the (low, high) 95% interval value +/- t95(dof) * std_unc."""
    if not (math.isfinite(std_unc) and std_unc >= 0):
        return Err(UncertaintyError.InvalidUncertainty)
    k = t95(dof)
    if isinstance(k, Err):
        return Err(k.danger_err)
    half = k.danger_ok * std_unc
    return Ok((value - half, value + half))


def relative_uncertainty(value: float, std_unc: float) -> Result[float, UncertaintyError]:
    """Return |std_unc / value|, or ZeroValue when value is zero."""
    if value == 0:
        _log.warning("relative uncertainty of zero value")
        return Err(UncertaintyError.ZeroValue)
    return Ok(abs(std_unc / value))


def effective_dof(
    contributions: Sequence[tuple[float, float | None]],
) -> Result[float, UncertaintyError]:
    """Welch-Satterthwaite dof from (|c_i| u_i, dof_i) pairs; None or inf dof terms add nothing.

    Returns inf when no contribution has finite dof, and also when the combined uncertainty is 0.
    """
    if not contributions:
        return Err(UncertaintyError.NoContributions)
    for u_i, dof_i in contributions:
        if not (math.isfinite(u_i) and u_i >= 0):
            return Err(UncertaintyError.InvalidUncertainty)
        if dof_i is not None and (math.isnan(dof_i) or dof_i <= 0):
            return Err(UncertaintyError.InvalidDof)
    # The ratio total^2 / denom is invariant under a common scale, so normalise by the largest
    # contribution: r**2 and r**4 then cannot overflow for any finite u_i.  frob:ticket 01M6WJQ4CCMWZCF8NK30FYTGN8
    scale = max(u for u, _ in contributions)
    if scale == 0.0:
        return Ok(math.inf)
    total = 0.0
    denom = 0.0
    for u_i, dof_i in contributions:
        r = u_i / scale
        total += r**2
        if dof_i is not None and math.isfinite(dof_i):
            denom += r**4 / dof_i
    if denom == 0.0:
        return Ok(math.inf)
    return Ok(total**2 / denom)
