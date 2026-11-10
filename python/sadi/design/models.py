"""Payloads and error codes of the sequential-design selector (docs/design/gp-selector.md)."""

# frob:ticket 01M72PGN2KAMZP8EPHDPV143B4

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from sadi.labs.lctt.gp_suggester import GpState
from sadi.synthetic.specimen import CopperSpec

__all__ = [
    "AltCandidate",
    "Candidate",
    "ConfidenceIndicator",
    "Criterion",
    "CurrentFit",
    "DesignAdvice",
    "DesignPhase",
    "GpState",
    "CapturedPoint",
    "Hang",
    "NextSuggestion",
    "PlanConfig",
    "PlanRequest",
    "Weight",
    "WeightPlan",
    "Obs",
    "SelectorConfig",
    "SelectorError",
    "TargetSpec",
]

SCHEMA_VERSION = 1


class DesignPhase(StrEnum):
    """Which model the design uses: LVDT calibration, elastic fit or yield GP."""

    LVDT_CAL = "lvdt_cal"
    ELASTIC = "elastic"
    YIELD = "yield"


class Criterion(StrEnum):
    """Acquisition criterion; `target` is c-optimal (expected shrink of the target interval)."""

    TARGET = "target"
    D_OPT = "d_opt"
    A_OPT = "a_opt"


class SelectorError(StrEnum):
    """Why the selector could not advise; the value is the plain-language hint."""

    NoCandidates = "There are no candidate loads to choose from"
    SingularPosterior = "The model could not be fitted to these points (degenerate data)"
    NonFinite = "A measurement or candidate is not a finite number"
    BudgetExceeded = "The suggestion took longer than its time budget"
    InvalidTarget = "The target half-width must be a finite number above zero"


class Candidate(BaseModel):
    """One allowed next setting (a load in kg, or a gauge height in m) with its own uncertainty."""

    model_config = ConfigDict(frozen=True)

    candidate_id: str
    x: float
    u_x: float = 0.0


class Obs(BaseModel):
    """One settled, confirmed observation: design variable x, response y, uncertainty u."""

    model_config = ConfigDict(frozen=True)

    x: float
    y: float
    u: float = 0.0


class TargetSpec(BaseModel):
    """User target half-width of the 95 % interval; relative to the estimate unless stated."""

    model_config = ConfigDict(frozen=True)

    half_width: float
    unit: str = ""
    relative: bool = True


class CurrentFit(BaseModel):
    """Current estimate of the target quantity; `half_width` is None while it cannot be formed."""

    model_config = ConfigDict(frozen=True)

    half_width: float | None
    value: float | None
    dof: float


class SelectorConfig(BaseModel):
    """Tunable selector settings (spec section 2 and 4 defaults)."""

    model_config = ConfigDict(frozen=True)

    patience: int = Field(default=2, ge=1)
    margin: float = Field(default=0.9, gt=0, le=1)
    eps: float = Field(default=0.02, ge=0)
    n_min_linear: int = Field(default=3, ge=3)
    n_min_yield: int = Field(default=5, ge=4)
    max_gp_points: int = Field(default=60, ge=8)
    max_window: int = Field(default=64, ge=4)
    budget_ms: float = 150.0
    criterion: Criterion = Criterion.TARGET
    #: 0.2 % offset expressed in response units (yield phase); required for the yield GP.
    offset_response: float | None = None


#: Stable machine codes naming why an indicator has no usable fit (the UI keys on these).
ReasonCode = Literal[
    "cold_start",
    "singular",
    "no_offset",
    "yield_not_reached",
    "departure_from_linear",
    "diminishing_returns",
    "no_elastic_fit",
    "no_calibration",
]


class ConfidenceIndicator(BaseModel):
    """The "confidence is enough" payload (advisory; the user always decides)."""

    model_config = ConfigDict(frozen=True)

    schema_version: int = SCHEMA_VERSION
    phase: DesignPhase
    job_version: int
    n: int
    target: TargetSpec
    current: CurrentFit
    ratio: float | None
    state: GpState
    consecutive_ok: int
    patience: int
    advisory: Literal[True] = True
    reasons: tuple[ReasonCode, ...] = ()


class AltCandidate(BaseModel):
    """A runner-up candidate with its expected gain."""

    model_config = ConfigDict(frozen=True)

    candidate_id: str
    x: float
    expected_gain: float


class NextSuggestion(BaseModel):
    """Recommended next candidate with the expected gain; never acts on the machine."""

    model_config = ConfigDict(frozen=True)

    schema_version: int = SCHEMA_VERSION
    phase: DesignPhase
    job_version: int
    candidate_id: str
    x: float
    unit: str
    expected_gain: float
    expected_half_width: float | None
    alternatives: tuple[AltCandidate, ...] = ()
    criterion: Criterion = Criterion.TARGET
    elapsed_ms: float = 0.0
    budget_exceeded: bool = False
    advisory: Literal[True] = True
    #: One plain-language sentence saying why this value was chosen (for students).
    why: str = ""


class DesignAdvice(BaseModel):
    """REST payload: the suggestion (None when there is nothing to suggest) plus the indicator."""

    model_config = ConfigDict(frozen=True)

    suggestion: NextSuggestion | None
    indicator: ConfidenceIndicator
    advisory: Literal[True] = True


# ---- weight plan (docs/design/weight-plan.md)
# frob:ticket 01M72X7S8DA8X3Q95HRYNKT2ED


class Weight(BaseModel):
    """One physical inventory weight; duplicates are distinct ids with their own uncertainty."""

    model_config = ConfigDict(frozen=True)

    weight_id: str
    mass_kg: float = Field(gt=0)
    u_mass_kg: float = Field(default=0.0, ge=0)


class CapturedPoint(BaseModel):
    """An already-captured hang (total mass and settled LVDT volts) used when replanning."""

    model_config = ConfigDict(frozen=True)

    mass_kg: float = Field(ge=0)
    volts: float
    u_volts: float = Field(default=0.0, ge=0)


class PlanConfig(BaseModel):
    """Planner settings; the material prior is the shared synthetic CopperSpec."""

    model_config = ConfigDict(frozen=True)

    copper: CopperSpec = CopperSpec()
    target: TargetSpec = TargetSpec(half_width=0.05)
    selector: SelectorConfig = SelectorConfig()
    #: Largest allowed tension as a fraction of the wire's ultimate load.
    capacity_fraction: float = Field(default=0.95, gt=0, le=1)
    #: Cap on the number of hangs reported; None means as many as there are usable loads.
    max_hangs: int | None = Field(default=None, ge=1)
    #: Mass keys are rounded to this many kg when deduplicating equal-mass multisets.
    mass_resolution_kg: float = Field(default=1e-9, gt=0)


class PlanRequest(BaseModel):
    """Everything plan() needs: inventory, wire geometry, LVDT calibration and prior points."""

    model_config = ConfigDict(frozen=True)

    weights: tuple[Weight, ...]
    diameter_m: float = Field(gt=0)
    u_diameter_m: float = Field(default=0.0, ge=0)
    length_m: float = Field(gt=0, description="gauge length L0")
    u_length_m: float = Field(default=0.0, ge=0)
    cal_slope_v_per_m: float
    cal_offset_v: float = 0.0
    saturation_v: float | None = Field(default=None, gt=0)
    captured: tuple[CapturedPoint, ...] = ()
    config: PlanConfig = PlanConfig()


class Hang(BaseModel):
    """One planned hang: which weights, their total, predicted volts and the gain it buys."""

    model_config = ConfigDict(frozen=True)

    order: int
    weight_ids: tuple[str, ...]
    total_mass_kg: float
    u_mass_kg: float
    tension_n: float
    predicted_volts: float
    u_predicted_volts: float
    expected_gain: float
    #: Slope half-width (V/kg) after this hang (elastic); None until a fit exists.
    slope_half_width_v_per_kg: float | None = None
    #: Modulus half-width (Pa) after this hang, geometry included (elastic).
    e_half_width_pa: float | None = None
    #: Yield-load half-width (kg) after this hang (yield phase).
    yield_half_width_kg: float | None = None
    reason: str = ""


class WeightPlan(BaseModel):
    """Ordered hangs for the remaining run; advisory only."""

    model_config = ConfigDict(frozen=True)

    phase: DesignPhase
    hangs: tuple[Hang, ...]
    n_inventory: int
    n_achievable: int
    n_usable: int
    dropped_saturation: int = 0
    dropped_capacity: int = 0
    advisory: Literal[True] = True
