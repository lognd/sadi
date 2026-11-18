"""LCTT guided run: per-phase next action, expected value, confidence and stop-early advice."""

# frob:ticket 01M6W7R3W8RJPVS0VVDG2YNMJB

from __future__ import annotations

import math
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field
from typani import Err, ErrorSet, Ok, Result

from sadi.core.results import ResultSet
from sadi.labs.lctt.calibration import MIN_POINTS as MIN_CAL_POINTS
from sadi.logging_setup import get_logger

_log = get_logger(__name__)

#: Maximum points per phase; the whole guided run is bounded by `MAX_RUN_POINTS`.
MAX_CAL_POINTS = 8
MAX_ELASTIC_POINTS = 12
MAX_PLASTIC_POINTS = 15
#: Documented hard bound on points in a complete three-phase guided run.
MAX_RUN_POINTS = MAX_CAL_POINTS + MAX_ELASTIC_POINTS + MAX_PLASTIC_POINTS
#: Fewest load points before a load phase may recommend stopping early.
MIN_LOAD_POINTS = 5


class GuidanceError(ErrorSet):
    """Guidance failure; the description says what to fix."""

    BadRange = "Load range must be finite with 0 <= min < max kg; fix the safe-load limits"
    BadTarget = "Confidence target must be a finite fraction > 0; enter e.g. 0.05"
    UnsafeLoad = "Suggester proposed a load outside the safe range; refusing to show it"
    SuggesterFailed = "The load suggester failed; fall back to the default schedule"
    NoNextPhase = "The run is already in its last phase; there is nothing to advance to"


class Phase(StrEnum):
    """Run phases in order: LVDT calibration, elastic (long wire), plastic (short wire)."""

    CALIBRATE = "calibrate"
    ELASTIC = "elastic"
    PLASTIC = "plastic"


_ORDER = (Phase.CALIBRATE, Phase.ELASTIC, Phase.PLASTIC)
_TRACKED = {Phase.CALIBRATE: "slope", Phase.ELASTIC: "E", Phase.PLASTIC: "yield_stress"}
_CAPS = {
    Phase.CALIBRATE: MAX_CAL_POINTS,
    Phase.ELASTIC: MAX_ELASTIC_POINTS,
    Phase.PLASTIC: MAX_PLASTIC_POINTS,
}


class HoldState(StrEnum):
    """Where the current point is: ready for the next, still creeping, or settled to accept."""

    READY = "ready"
    CREEPING = "creeping"
    AWAITING_ACCEPT = "awaiting_accept"


class LoadRange(BaseModel):
    """Allowed (safe) hanging mass range in kg, inclusive."""

    model_config = ConfigDict(frozen=True)

    min_kg: float
    max_kg: float

    def contains(self, kg: float) -> bool:
        """True when `kg` is finite and inside the inclusive range."""
        return math.isfinite(kg) and self.min_kg <= kg <= self.max_kg


def make_range(min_kg: float, max_kg: float) -> Result[LoadRange, GuidanceError]:
    """Build a LoadRange, rejecting non-finite, negative or empty ranges."""
    if not (math.isfinite(min_kg) and math.isfinite(max_kg)) or min_kg < 0 or min_kg >= max_kg:
        _log.warning("make_range: rejected [%r, %r]", min_kg, max_kg)
        return Err(GuidanceError.BadRange)
    return Ok(LoadRange(min_kg=min_kg, max_kg=max_kg))


class LoadSuggestion(BaseModel):
    """A suggested total load (kg) and the human text describing how to build it."""

    model_config = ConfigDict(frozen=True)

    load_kg: float
    text: str
    expected_gain: float | None = None
    expected_half_width: float | None = None
    alternatives: tuple[float, ...] = ()
    gp_state: str = ""


class LoadSuggester(Protocol):
    """Pluggable source of the next load; any object with this `suggest` method works."""

    def suggest(
        self, phase: Phase, results: ResultSet, load_range: LoadRange
    ) -> Result[LoadSuggestion, GuidanceError]:
        """Propose the next load within `load_range` for `phase` given the current results."""
        ...


def mass_guidance_text(kg: float) -> str:
    """The one shared guidance wording: masses only, because the hanger is added for you."""
    return f"Add {kg:.3f} kg of masses to the hanger (the hanger is added for you)"


class EvenScheduleSuggester:
    """Default suggester: step evenly from the range minimum up to its maximum."""

    def suggest(
        self, phase: Phase, results: ResultSet, load_range: LoadRange
    ) -> Result[LoadSuggestion, GuidanceError]:
        """Return step k+1 of an even schedule over the phase point cap (k = points taken)."""
        cap = _CAPS[phase]
        k = min(results.n_points, cap - 1)
        span = load_range.max_kg - load_range.min_kg
        kg = min(load_range.max_kg, load_range.min_kg + span * (k + 1) / cap)
        return Ok(
            LoadSuggestion(
                load_kg=kg,
                text=mass_guidance_text(kg),
            )
        )


class GuidanceConfig(BaseModel):
    """User settings: relative half-width target, safe load range and per-phase min points."""

    model_config = ConfigDict(frozen=True)

    target: float = Field(default=0.05, description="Target relative 95 % half-width")
    load_range: LoadRange = LoadRange(min_kg=0.0, max_kg=5.0)
    min_load_points: int = Field(default=MIN_LOAD_POINTS, ge=3)


def check_target(target: float) -> Result[float, GuidanceError]:
    """Validate a confidence target fraction."""
    if not math.isfinite(target) or target <= 0:
        _log.warning("check_target: rejected %r", target)
        return Err(GuidanceError.BadTarget)
    return Ok(target)


class GuidanceInput(BaseModel):
    """What the guide needs to know now: live results, calibration count and hold state."""

    model_config = ConfigDict(frozen=True)

    results: ResultSet
    n_cal_points: int = 0
    hold: HoldState = HoldState.READY


class Confidence(BaseModel):
    """Running confidence: current 95 % half-width against the user's target."""

    model_config = ConfigDict(frozen=True)

    quantity: str
    half_width: float | None = None
    target_half_width: float | None = None
    relative: float | None = None
    fraction: float = Field(default=0.0, ge=0.0, le=1.0, description="Progress to target")
    met: bool = False


class GuidanceState(BaseModel):
    """Everything the guidance panel shows for one phase after one point."""

    model_config = ConfigDict(frozen=True)

    phase: Phase
    next_action: str
    suggested_load_kg: float | None = None
    expected_value: float | None = None
    unit: str = ""
    confidence: Confidence
    points_taken: int
    max_points: int
    stop_early: bool = False
    stop_reason: str = ""
    proposed_next_phase: Phase | None = None
    run_complete_proposed: bool = False
    # frob:ticket 01M71KCTETKE1AE0GZ35MQ11EV
    expected_gain: float | None = None
    expected_half_width: float | None = None
    alternatives: tuple[float, ...] = ()
    gp_state: str = ""


def _confidence(phase: Phase, results: ResultSet, target: float) -> Confidence:
    """Compare the phase's key result half-width (u95) with the target * |value|."""
    name = _TRACKED[phase]
    val = results.get(name)
    if val is None or val.value == 0 or not math.isfinite(val.u95):
        return Confidence(quantity=name)
    rel = val.u95 / abs(val.value)
    return Confidence(
        quantity=name,
        half_width=val.u95,
        target_half_width=target * abs(val.value),
        relative=rel,
        fraction=min(1.0, target / rel) if rel > 0 else 1.0,
        met=rel <= target,
    )


def _next_action(  # noqa: PLR0913
    phase: Phase,
    inp: GuidanceInput,
    cfg: GuidanceConfig,
    suggester: LoadSuggester,
    exhausted: bool,
) -> Result[tuple[str, float | None, LoadSuggestion | None], GuidanceError]:
    """Pick the next-action text (and safe suggested load) for the current hold state."""
    if inp.hold is HoldState.CREEPING:
        return Ok(("Wait: creeping", None, None))
    if inp.hold is HoldState.AWAITING_ACCEPT:
        return Ok(("Press Space to accept", None, None))
    if exhausted:
        return Ok(("Point budget reached: accept the phase or finish", None, None))
    if phase is Phase.CALIBRATE:
        return Ok((f"Record calibration point {inp.n_cal_points + 1}", None, None))
    got = suggester.suggest(phase, inp.results, cfg.load_range)
    if isinstance(got, Err):
        _log.warning("suggester failed in %s: %s", phase, got.danger_err)
        return Err(GuidanceError.SuggesterFailed)
    sug = got.danger_ok
    if not cfg.load_range.contains(sug.load_kg):
        _log.error("unsafe suggestion %r kg outside %s", sug.load_kg, cfg.load_range)
        return Err(GuidanceError.UnsafeLoad)
    return Ok((sug.text, sug.load_kg, sug))


def guide(
    phase: Phase,
    inp: GuidanceInput,
    cfg: GuidanceConfig | None = None,
    suggester: LoadSuggester | None = None,
) -> Result[GuidanceState, GuidanceError]:
    """Compute the guidance for `phase`; a phase change is only ever proposed, never applied."""
    conf = cfg or GuidanceConfig()
    checked = check_target(conf.target)
    if isinstance(checked, Err):
        return Err(checked.danger_err)
    taken = inp.n_cal_points if phase is Phase.CALIBRATE else inp.results.n_points
    cap = _CAPS[phase]
    minimum = MIN_CAL_POINTS if phase is Phase.CALIBRATE else conf.min_load_points
    confidence = _confidence(phase, inp.results, conf.target)
    exhausted = taken >= cap
    enough = taken >= minimum and confidence.met
    stop = enough or exhausted
    reason = ""
    if exhausted and not enough:
        reason = f"Point budget of {cap} reached before the target was met"
    elif enough:
        reason = f"{confidence.quantity} half-width is within the {conf.target:.1%} target"
    if suggester is None:
        from sadi.labs.lctt.gp_suggester import GpLoadSuggester  # noqa: PLC0415 (import cycle)

        suggester = GpLoadSuggester()
    act = _next_action(phase, inp, conf, suggester, exhausted)
    if isinstance(act, Err):
        return Err(act.danger_err)
    text, load, sug = act.danger_ok
    idx = _ORDER.index(phase)
    nxt = _ORDER[idx + 1] if idx + 1 < len(_ORDER) else None
    expected = inp.results.get(_TRACKED[phase])
    state = GuidanceState(
        phase=phase,
        next_action=text,
        suggested_load_kg=load,
        expected_value=expected.value if expected else None,
        unit=expected.unit if expected else "",
        confidence=confidence,
        points_taken=taken,
        max_points=cap,
        stop_early=stop and not exhausted,
        stop_reason=reason if stop else "",
        proposed_next_phase=nxt if stop else None,
        run_complete_proposed=stop and nxt is None,
        expected_gain=sug.expected_gain if sug else None,
        expected_half_width=sug.expected_half_width if sug else None,
        alternatives=sug.alternatives if sug else (),
        gp_state="enough" if (stop and sug) else (sug.gp_state if sug else ""),
    )
    _log.debug("guide: %s taken=%d stop=%s action=%r", phase, taken, stop, text)
    return Ok(state)


class GuidedRun:
    """Holds the current phase; moves on only when the user calls `accept_transition`."""

    def __init__(
        self, cfg: GuidanceConfig | None = None, suggester: LoadSuggester | None = None
    ) -> None:
        """Start in the calibrate phase with the given settings and suggester."""
        self._cfg = cfg or GuidanceConfig()
        if suggester is None:
            from sadi.labs.lctt.gp_suggester import GpLoadSuggester  # noqa: PLC0415 (import cycle)

            suggester = GpLoadSuggester()
        self._suggester: LoadSuggester = suggester
        self._phase = Phase.CALIBRATE

    @property
    def suggester(self) -> LoadSuggester:
        """The load suggester in use (a GpLoadSuggester unless one was injected)."""
        return self._suggester

    @property
    def phase(self) -> Phase:
        """The phase the user is currently in."""
        return self._phase

    def guide(self, inp: GuidanceInput) -> Result[GuidanceState, GuidanceError]:
        """Guidance for the current phase; calling it never changes the phase."""
        return guide(self._phase, inp, self._cfg, self._suggester)

    def accept_transition(self) -> Result[Phase, GuidanceError]:
        """Explicitly advance to the next phase (the user accepted a proposal)."""
        idx = _ORDER.index(self._phase)
        if idx + 1 >= len(_ORDER):
            return Err(GuidanceError.NoNextPhase)
        self._phase = _ORDER[idx + 1]
        _log.info("guided run: advanced to %s", self._phase)
        return Ok(self._phase)
