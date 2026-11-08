"""LCTT pre-test clamp-slip check: small load, hold, unload, repeat; slip + zero-return verdict."""

# frob:ticket 01M6W7R2TPG1HC0F9QHDQ1C3W6

from __future__ import annotations

import math
from collections.abc import Sequence

from pydantic import BaseModel, Field
from typani import Err, ErrorSet, Ok, Result

from sadi.labs.lctt.slip import SlipConfig, SlipError, SlipEvent, detect_slip
from sadi.logging_setup import get_logger

_log = get_logger(__name__)

SETUP_STEP_ID = "setup"
SETUP_SUBCHECK_ID = "clamp-slip"
ADVICE_RETIGHTEN = "Re-tighten clamps, then repeat the clamp-slip check before testing."
ADVICE_OK = "Clamps look secure: no slip and strain returned to zero. Proceed."


class ClampCheckError(ErrorSet):
    """Unusable clamp-check input; the description says what to fix."""

    NoCycles = "At least one load/hold/unload cycle is required; run the procedure first"
    NonFinite = "Zero readings must be finite; re-take the pre-load and post-unload zeros"
    BadHold = "A cycle hold could not be analysed; see the log for the slip detector reason"


class ClampCheckConfig(BaseModel):
    """Frozen procedure parameters: small-load level, hold time, cycle count, tolerances."""

    model_config = {"frozen": True}

    load_fraction: float = Field(default=0.1, gt=0, le=0.5, description="Fraction of test load")
    hold_s: float = Field(default=30.0, gt=0, description="Seconds to hold each small load")
    cycles: int = Field(default=3, ge=1, le=20, description="Load/hold/unload repetitions")
    return_tol: float = Field(default=2e-5, ge=0, description="Max |zero shift| (strain) per cycle")
    slip: SlipConfig = Field(default_factory=SlipConfig, description="Slip detector settings")


class ClampCycle(BaseModel):
    """One cycle: hold samples after loading at t_load, plus the zeros before and after it."""

    model_config = {"frozen": True}

    t_load: float
    times: tuple[float, ...]
    strain: tuple[float, ...]
    load: tuple[float, ...] | None = None
    zero_before: float
    zero_after: float


class CycleVerdict(BaseModel):
    """Per-cycle outcome: slip events found, zero shift and whether the cycle passed."""

    model_config = {"frozen": True}

    index: int
    events: tuple[SlipEvent, ...]
    zero_shift: float
    returned: bool
    passed: bool


class ClampCheckReport(BaseModel):
    """Overall verdict with per-cycle detail and operator advice (empty-safe, never None)."""

    model_config = {"frozen": True}

    passed: bool
    cycles: tuple[CycleVerdict, ...]
    advice: str


class SetupSubCheck(BaseModel):
    """Descriptor wiring this check into the wizard 'Setup' step as a sub-check."""

    model_config = {"frozen": True}

    step_id: str = SETUP_STEP_ID
    check_id: str = SETUP_SUBCHECK_ID
    title: str = "Clamp slip check"
    guidance: str


def setup_subcheck(config: ClampCheckConfig | None = None) -> SetupSubCheck:
    """Return the wizard Setup-step sub-check descriptor with the procedure as guidance."""
    cfg = config or ClampCheckConfig()
    text = (
        f"Apply about {cfg.load_fraction:.0%} of the test load, hold {cfg.hold_s:g} s, "
        f"unload to zero; repeat {cfg.cycles} times, then capture each cycle."
    )
    return SetupSubCheck(guidance=text)


def _judge(i: int, cyc: ClampCycle, cfg: ClampCheckConfig) -> Result[CycleVerdict, ClampCheckError]:
    """Run the slip detector on one cycle and test the zero return."""
    if not (math.isfinite(cyc.zero_before) and math.isfinite(cyc.zero_after)):
        _log.error("cycle %d: non-finite zero reading", i)
        return Err(ClampCheckError.NonFinite)
    res = detect_slip(cyc.times, cyc.strain, cyc.t_load, cyc.load, cfg.slip)
    if not isinstance(res, Ok):
        err: SlipError = res.unwrap_err()
        _log.error("cycle %d: slip detector rejected hold: %s", i, err.name)
        return Err(ClampCheckError.BadHold)
    events = res.value.events
    shift = cyc.zero_after - cyc.zero_before
    returned = abs(shift) <= cfg.return_tol
    passed = returned and not events
    _log.info(
        "cycle %d: events=%d shift=%g returned=%s passed=%s",
        i,
        len(events),
        shift,
        returned,
        passed,
    )
    return Ok(
        CycleVerdict(index=i, events=events, zero_shift=shift, returned=returned, passed=passed)
    )


def check_clamp_slip(
    cycles: Sequence[ClampCycle], config: ClampCheckConfig | None = None
) -> Result[ClampCheckReport, ClampCheckError]:
    """Pass only if every cycle is slip-free and returns to zero within tolerance."""
    cfg = config or ClampCheckConfig()
    if not cycles:
        _log.error("clamp check called with no cycles")
        return Err(ClampCheckError.NoCycles)
    verdicts: list[CycleVerdict] = []
    for i, cyc in enumerate(cycles):
        res = _judge(i, cyc, cfg)
        if not isinstance(res, Ok):
            return Err(res.unwrap_err())
        verdicts.append(res.value)
    passed = all(v.passed for v in verdicts)
    advice = ADVICE_OK if passed else ADVICE_RETIGHTEN
    _log.info("clamp check %s over %d cycles", "PASS" if passed else "FAIL", len(verdicts))
    return Ok(ClampCheckReport(passed=passed, cycles=tuple(verdicts), advice=advice))
