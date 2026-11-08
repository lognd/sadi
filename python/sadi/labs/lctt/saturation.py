"""LCTT ADC saturation flags: any |V| above the configurable threshold warns on that point."""

# frob:ticket 01M6W7R3BBDEXG9CPYWTQ7ZKZW

from __future__ import annotations

import math
from collections.abc import Sequence

from pydantic import BaseModel, Field
from typani import Err, ErrorSet, Ok, Result

from sadi.logging_setup import get_logger

_log = get_logger(__name__)

DEFAULT_SATURATION_V = 4.9
"""Warning threshold in volts; mounting guidance says 4.8, the ADC range is 5.12 (Q14)."""


class SaturationError(ErrorSet):
    """Saturation check failure; the description says what to fix."""

    NonFinite = "Samples must be finite; drop or repair NaN/inf readings"
    BadThreshold = "Saturation threshold must be finite and > 0 volts"


class SaturationConfig(BaseModel):
    """Frozen saturation threshold in volts (default 4.9 on a 5.12 V range)."""

    model_config = {"frozen": True}

    threshold_v: float = Field(default=DEFAULT_SATURATION_V, gt=0, le=10)


class SaturationFlag(BaseModel):
    """Typed per-point warning: largest |V| seen, the threshold, and whether it saturated."""

    model_config = {"frozen": True}

    point_index: int
    max_abs_v: float
    threshold_v: float
    saturated: bool

    @property
    def message(self) -> str:
        """Human warning text, empty when the point is clean."""
        if not self.saturated:
            return ""
        return (
            f"point {self.point_index}: |V| {self.max_abs_v:.3f} exceeds "
            f"{self.threshold_v:.2f} V; the ADC may be clipping"
        )


def check_saturation(
    point_index: int, volts: Sequence[float], config: SaturationConfig | None = None
) -> Result[SaturationFlag, SaturationError]:
    """Flag a point whose raw samples include any |V| > threshold."""
    cfg = config or SaturationConfig()
    if not volts or not all(math.isfinite(v) for v in volts):
        _log.warning("check_saturation: point %d has empty or non-finite samples", point_index)
        return Err(SaturationError.NonFinite)
    peak = max(abs(v) for v in volts)
    flag = SaturationFlag(
        point_index=point_index,
        max_abs_v=peak,
        threshold_v=cfg.threshold_v,
        saturated=peak > cfg.threshold_v,
    )
    if flag.saturated:
        _log.warning("check_saturation: %s", flag.message)
    else:
        _log.debug("check_saturation: point %d peak %.3f V ok", point_index, peak)
    return Ok(flag)
