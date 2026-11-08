"""LCTT tare pooling plus load, stress and strain with full-covariance RSS uncertainty."""

# frob:ticket 01M6W7R2XY9DB0PFREY9TZ8D2S

from __future__ import annotations

import math
from collections.abc import Sequence
from enum import StrEnum

from pydantic import BaseModel, Field
from typani import Err, ErrorSet, Ok, Result

from sadi.logging_setup import get_logger
from sadi.uncertainty import Measured, Provenance, UncertainError, UncertaintyError, uncertain

_log = get_logger(__name__)

SHORT_L0_M = 0.08313
LONG_L0_M = 0.5
STANDARD_G = 9.80665
_VOLT = "V"
_SLOPE = "m/V"
_METRE = "m"
_KG = "kg"
_ACCEL = "m/s**2"


class LoadingError(ErrorSet):
    """Loading computation failure; the description says what to fix."""

    NoBlocks = "Need at least one tare block; capture the tare again"
    LengthMismatch = "Block means, sds and counts must have equal length"
    BadBlock = "Each tare block needs a finite mean, a finite sd >= 0 and n >= 2 samples"
    TooFewSamples = "Pooled tare needs more than one sample in total; capture more"
    BadInput = "Input must be finite and its uncertainty >= 0; fix the entry"
    BadLength = "Gauge length L0 and diameter must be finite and > 0; enter real values"
    Propagation = "Uncertainty propagation failed; check units and inputs"


class VoltageUncertainty(StrEnum):
    """How a block's voltage uncertainty is formed (Q5)."""

    TWO_S = "two_s"
    TWO_S_OVER_SQRT_N = "two_s_over_sqrt_n"


class SignPolicy(StrEnum):
    """What to do about an LVDT slope of the wrong sign (Q10)."""

    WARN = "warn"
    FLIP = "flip"


class Specimen(StrEnum):
    """Specimen kind selecting the default gauge length (Q8)."""

    SHORT = "short"
    LONG = "long"


def default_l0(specimen: Specimen) -> float:
    """Default gauge length L0 in metres for a specimen kind; callers may always override."""
    return SHORT_L0_M if specimen is Specimen.SHORT else LONG_L0_M


class LoadingOptions(BaseModel):
    """Frozen options with documented defaults: U_V rule (Q5), sign policy (Q10), specimen (Q8)."""

    model_config = {"frozen": True}

    voltage_uncertainty: VoltageUncertainty = Field(
        default=VoltageUncertainty.TWO_S, description="U_V = 2 s of the block (Q5 default)"
    )
    sign_policy: SignPolicy = Field(
        default=SignPolicy.WARN, description="Warn on a negative slope; FLIP negates it (Q10)"
    )
    specimen: Specimen = Field(default=Specimen.SHORT, description="Selects default L0 (Q8)")
    l0: float | None = Field(default=None, gt=0, description="L0 override in metres; None=default")

    @property
    def gauge_length(self) -> float:
        """Effective L0 in metres: the override when set, else the specimen default."""
        return self.l0 if self.l0 is not None else default_l0(self.specimen)


class LoadingInputs(BaseModel):
    """Measured inputs for one captured point; masses are the inventory weights on the hanger."""

    model_config = {"frozen": True, "arbitrary_types_allowed": True}

    voltage: Measured
    tare: Measured
    slope: Measured
    masses: tuple[Measured, ...]
    hanger: Measured
    diameter: Measured
    l0: Measured | None = None
    g: Measured | None = None


class LoadingResult(BaseModel):
    """Load, stress and strain Measured values plus any warnings raised on the way."""

    model_config = {"frozen": True}

    load: Measured
    area: Measured
    stress: Measured
    strain: Measured
    warnings: tuple[str, ...] = ()


@uncertain
def load_force(mass_total, hanger_mass, g):  # type: ignore[no-untyped-def]  # noqa: ANN001, ANN201
    """Load F = (sum of inventory masses + hanger) * g."""
    return (mass_total + hanger_mass) * g


@uncertain
def cross_area(diameter):  # type: ignore[no-untyped-def]  # noqa: ANN001, ANN201
    """Cross-section area A = pi d^2 / 4."""
    return 3.141592653589793 * diameter**2 / 4


@uncertain
def stress(force, area):  # type: ignore[no-untyped-def]  # noqa: ANN001, ANN201
    """Stress sigma = F / A."""
    return force / area


@uncertain
def strain(slope, volts, tare, l0):  # type: ignore[no-untyped-def]  # noqa: ANN001, ANN201
    """Strain eps = slope * (V - V_tare) / L0."""
    return slope * (volts - tare) / l0


def block_voltage(
    mean: float,
    sd: float,
    n: int,
    rule: VoltageUncertainty = VoltageUncertainty.TWO_S,
) -> Result[Measured, LoadingError]:
    """Voltage Measured of one block: mean with U_V = 2 s (or 2 s / sqrt(n), Q5)."""
    if not (math.isfinite(mean) and math.isfinite(sd) and sd >= 0 and n >= 1):
        _log.warning("block_voltage: bad block mean=%r sd=%r n=%r", mean, sd, n)
        return Err(LoadingError.BadBlock)
    u = 2.0 * sd if rule is VoltageUncertainty.TWO_S else 2.0 * sd / math.sqrt(n)
    return _make(mean, u, _VOLT, f"block_voltage[{rule.value}]")


def pool_tare(
    means: Sequence[float], sds: Sequence[float], counts: Sequence[int]
) -> Result[Measured, LoadingError]:
    """Pool B tare blocks (domain 3.2): M = mean of means, U_tare = 2 Sx."""
    if not means:
        return Err(LoadingError.NoBlocks)
    if not (len(means) == len(sds) == len(counts)):
        return Err(LoadingError.LengthMismatch)
    if not all(
        math.isfinite(m) and math.isfinite(s) and s >= 0 and c >= 2
        for m, s, c in zip(means, sds, counts, strict=True)
    ):
        _log.warning("pool_tare: invalid block among %d", len(means))
        return Err(LoadingError.BadBlock)
    total = sum(counts)
    if total < 2:
        return Err(LoadingError.TooFewSamples)
    grand = sum(m * c for m, c in zip(means, counts, strict=True)) / total
    ss = sum(
        (c - 1) * s**2 + c * (m - grand) ** 2 for m, s, c in zip(means, sds, counts, strict=True)
    )
    sx = math.sqrt(ss / (total - 1))
    _log.info("pool_tare: %d blocks N=%d M=%g Sx=%g", len(means), total, grand, sx)
    return _make(grand, 2.0 * sx, _VOLT, "pool_tare")


def resolve_slope(
    slope: Measured, policy: SignPolicy
) -> Result[tuple[Measured, tuple[str, ...]], LoadingError]:
    """Apply the sign policy: warn on a negative slope, or negate it when FLIP (Q10)."""
    if slope.value >= 0:
        return Ok((slope, ()))
    if policy is SignPolicy.FLIP:
        flipped = slope.neg()
        if isinstance(flipped, Err):
            return Err(LoadingError.Propagation)
        _log.info("resolve_slope: negative slope %g flipped", slope.value)
        return Ok((flipped.danger_ok, ("LVDT slope was negative; sign flipped",)))
    _log.warning("resolve_slope: negative slope %g kept (policy warn)", slope.value)
    return Ok((slope, ("LVDT slope is negative: stretching reads as negative strain; flip it",)))


def compute_loading(
    inputs: LoadingInputs, options: LoadingOptions | None = None
) -> Result[LoadingResult, LoadingError]:
    """Compute load, area, stress and strain for one point, all through the uncertain engine."""
    opts = options or LoadingOptions()
    if not inputs.masses:
        _log.debug("compute_loading: no masses on hanger; load is hanger only")
    if not all(math.isfinite(v) for v in (opts.gauge_length, inputs.diameter.value)) or (
        inputs.diameter.value <= 0
    ):
        return Err(LoadingError.BadLength)
    resolved = resolve_slope(inputs.slope, opts.sign_policy)
    if isinstance(resolved, Err):
        return Err(resolved.danger_err)
    slope, warnings = resolved.danger_ok
    l0_m = inputs.l0
    if l0_m is None:
        made = _make(opts.gauge_length, 0.0, _METRE, "l0")
        if isinstance(made, Err):
            return made
        l0_m = made.danger_ok
    g_m = inputs.g
    if g_m is None:
        made = _make(STANDARD_G, 0.0, _ACCEL, "g")
        if isinstance(made, Err):
            return made
        g_m = made.danger_ok
    mass = _sum_masses(inputs.masses)
    if isinstance(mass, Err):
        return Err(mass.danger_err)
    steps = (
        load_force(mass.danger_ok, inputs.hanger, g_m),
        cross_area(inputs.diameter),
    )
    for step in steps:
        if isinstance(step, Err):
            return _propagation(step.danger_err)
    force, area = steps[0].danger_ok, steps[1].danger_ok  # type: ignore[union-attr]
    sig = stress(force, area)
    eps = strain(slope, inputs.voltage, inputs.tare, l0_m)
    for out in (sig, eps):
        if isinstance(out, Err):
            return _propagation(out.danger_err)
    _log.info(
        "compute_loading: F=%g sigma=%g eps=%g",
        force.value,
        sig.danger_ok.value,
        eps.danger_ok.value,
    )
    return Ok(
        LoadingResult(
            load=force, area=area, stress=sig.danger_ok, strain=eps.danger_ok, warnings=warnings
        )
    )


def latex_forms() -> Result[dict[str, str], UncertainError]:
    """LaTeX of load, stress and strain for the results panel and report."""
    out: dict[str, str] = {}
    for name, fn in (("load", load_force), ("stress", stress), ("strain", strain)):
        tex = fn.latex
        if isinstance(tex, Err):
            return Err(tex.danger_err)
        out[name] = tex.danger_ok
    return Ok(out)


def _make(value: float, unc: float, unit: str, source: str) -> Result[Measured, LoadingError]:
    """Build a Measured, mapping engine errors to BadInput."""
    made = Measured.create(value, unc, unit, provenance=Provenance(source=source))
    if isinstance(made, Err):
        _log.warning("%s: invalid value=%r unc=%r", source, value, unc)
        return Err(LoadingError.BadInput)
    return Ok(made.danger_ok)


def _sum_masses(masses: Sequence[Measured]) -> Result[Measured, LoadingError]:
    """Sum inventory masses with RSS uncertainty (zero Measured when there are none)."""
    total = _make(0.0, 0.0, _KG, "mass_total")
    if isinstance(total, Err):
        return total
    acc = total.danger_ok
    for m in masses:
        nxt = acc.add(m)
        if isinstance(nxt, Err):
            _log.warning("sum_masses: %s", nxt.danger_err)
            return Err(LoadingError.Propagation)
        acc = nxt.danger_ok
    return Ok(acc)


def _propagation(err: UncertainError | UncertaintyError | object) -> Err[LoadingError]:  # type: ignore[type-arg]
    """Log an engine error and return the Propagation Err."""
    _log.warning("propagation failed: %s", err)
    return Err(LoadingError.Propagation)
