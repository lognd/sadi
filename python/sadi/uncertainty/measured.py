"""Measured: a value with standard uncertainty, SI unit, covariance links and provenance."""

# frob:ticket 01M6W7R155JD0XGVXHDSP19B1H
# frob:ticket 01M72YKF3EN8RJX7RCH78JDPQC

from __future__ import annotations

import math
import uuid
import weakref
from collections.abc import Sequence

from pydantic import BaseModel, Field, field_validator
from typani import Err, Ok, Result

from sadi.logging_setup import get_logger
from sadi.uncertainty import coverage, units
from sadi.uncertainty.covariance import DEFAULT_REGISTRY, CovarianceRegistry
from sadi.uncertainty.errors import UncertaintyError

_log = get_logger(__name__)


class Provenance(BaseModel):
    """Where a number came from: a source event / WAL seq, or a derivation and its parents."""

    model_config = {"frozen": True}

    source: str = "manual"
    wal_seq: int | None = None
    derivation: str | None = None
    parents: tuple[str, ...] = ()


def _track(m: Measured, registry: CovarianceRegistry) -> None:
    """Tie the registry entry of `m` to its lifetime so dead quantities are forgotten."""
    registry.retain(m.id)
    weakref.finalize(m, registry.release, m.id)


class Measured(BaseModel):
    """A quantity in SI units: value, standard uncertainty, optional dof, id and provenance.

    Binary operators (+ - * /) and `power` return `Result[Measured, UncertaintyError]`
    and never raise; chain them with `.and_then`.
    """

    model_config = {"frozen": True}

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    value: float
    std_unc: float = 0.0
    unit: str = units.DIMENSIONLESS
    dof: float | None = None
    provenance: Provenance = Field(default_factory=Provenance)

    @field_validator("value")
    @classmethod
    def _finite_value(cls, v: float) -> float:
        """Reject NaN and infinite values."""
        if not math.isfinite(v):
            raise ValueError(str(UncertaintyError.InvalidValue))
        return v

    @field_validator("std_unc")
    @classmethod
    def _valid_unc(cls, v: float) -> float:
        """Reject negative or non-finite standard uncertainty."""
        if not (math.isfinite(v) and v >= 0):
            raise ValueError(str(UncertaintyError.InvalidUncertainty))
        return v

    @field_validator("dof")
    @classmethod
    def _valid_dof(cls, v: float | None) -> float | None:
        """Reject non-positive dof; inf is normalised to None (exact / Type B)."""
        if v is None or math.isinf(v):
            return None
        if math.isnan(v) or v <= 0:
            raise ValueError(str(UncertaintyError.InvalidDof))
        return v

    # ---- construction -------------------------------------------------

    @classmethod
    def create(
        cls,
        value: float,
        std_unc: float,
        unit: str = units.DIMENSIONLESS,
        *,
        dof: float | None = None,
        provenance: Provenance | None = None,
        registry: CovarianceRegistry = DEFAULT_REGISTRY,
    ) -> Result[Measured, UncertaintyError]:
        """Build a Measured from `unit`-valued inputs, converting to SI and registering it."""
        if not math.isfinite(value):
            return Err(UncertaintyError.InvalidValue)
        if not (math.isfinite(std_unc) and std_unc >= 0):
            return Err(UncertaintyError.InvalidUncertainty)
        if dof is not None and not math.isinf(dof) and (math.isnan(dof) or dof <= 0):
            return Err(UncertaintyError.InvalidDof)
        si = units.to_si(value, std_unc, unit)
        if isinstance(si, Err):
            return Err(si.danger_err)
        si_value, si_unc, si_unit = si.danger_ok
        out = cls(
            value=si_value,
            std_unc=si_unc,
            unit=si_unit,
            dof=dof,
            provenance=provenance or Provenance(),
        )
        registry.register(out.id, out.std_unc**2)
        _track(out, registry)
        _log.info("created %s = %g +/- %g %s", out.id, out.value, out.std_unc, out.unit)
        return Ok(out)

    @classmethod
    def from_readings(
        cls,
        readings: Sequence[float],
        u_instrument: float = 0.0,
        unit: str = units.DIMENSIONLESS,
        *,
        provenance: Provenance | None = None,
        registry: CovarianceRegistry = DEFAULT_REGISTRY,
    ) -> Result[Measured, UncertaintyError]:
        """Mean of repeated readings with standard uncertainty sqrt((s/sqrt n)^2 + u_instrument^2).

        The standard (k=1) type-A term is s/sqrt(n); dof is n-1 (None for one reading).
        """
        n = len(readings)
        if n == 0:
            return Err(UncertaintyError.NoContributions)
        if not all(math.isfinite(x) for x in readings):
            return Err(UncertaintyError.InvalidValue)
        if not (math.isfinite(u_instrument) and u_instrument >= 0):
            return Err(UncertaintyError.InvalidUncertainty)
        mean = math.fsum(readings) / n
        type_a = 0.0
        if n > 1:
            var = math.fsum((x - mean) ** 2 for x in readings) / (n - 1)
            type_a = math.sqrt(var / n)
        _log.info("from_readings n=%d mean=%g", n, mean)
        return cls.create(
            mean,
            math.hypot(type_a, u_instrument),
            unit,
            dof=(n - 1) if n > 1 else None,
            provenance=provenance or Provenance(source="repeated-readings"),
            registry=registry,
        )

    @classmethod
    def from_json(
        cls, text: str, registry: CovarianceRegistry = DEFAULT_REGISTRY
    ) -> Result[Measured, UncertaintyError]:
        """Parse the output of `to_json` and register its variance; BadJson on failure."""
        parsed = Result.catch(
            lambda: cls.model_validate_json(text),
            Exception,
            on_error=lambda exc: UncertaintyError.BadJson,
        )
        if isinstance(parsed, Ok):
            m = parsed.danger_ok
            if not registry.known(m.id):
                registry.register(m.id, m.std_unc**2)
            _track(m, registry)
        else:
            _log.warning("from_json failed")
        return parsed

    def to_json(self) -> str:
        """Serialise to JSON (round-trips through `from_json`; covariances are not included)."""
        return self.model_dump_json()

    # ---- statistics ---------------------------------------------------

    def covariance_with(
        self, other: Measured, registry: CovarianceRegistry = DEFAULT_REGISTRY
    ) -> float:
        """Return cov(self, other) from the registry."""
        return registry.covariance(self.id, other.id)

    def correlate(
        self, other: Measured, rho: float, registry: CovarianceRegistry = DEFAULT_REGISTRY
    ) -> Result[None, UncertaintyError]:
        """Declare correlation `rho` between self and other in the registry."""
        return registry.set_correlation(self.id, other.id, rho)

    def relative_uncertainty(self) -> Result[float, UncertaintyError]:
        """Return |std_unc / value|, or ZeroValue."""
        return coverage.relative_uncertainty(self.value, self.std_unc)

    def interval95(self) -> Result[tuple[float, float], UncertaintyError]:
        """Return the 95% interval using this quantity's dof."""
        return coverage.interval95(self.value, self.std_unc, self.dof)

    # ---- arithmetic ---------------------------------------------------

    def add(self, other: Measured | float) -> Result[Measured, UncertaintyError]:
        """Return self + other; units must share a dimension."""
        return _additive(self, other, +1.0, "add")

    def sub(self, other: Measured | float) -> Result[Measured, UncertaintyError]:
        """Return self - other; units must share a dimension."""
        return _additive(self, other, -1.0, "sub")

    def mul(self, other: Measured | float) -> Result[Measured, UncertaintyError]:
        """Return self * other with first-order full-covariance propagation."""
        return _multiplicative(self, other, "*", "mul")

    def div(self, other: Measured | float) -> Result[Measured, UncertaintyError]:
        """Return self / other; DomainError when other is zero."""
        return _multiplicative(self, other, "/", "div")

    def power(self, exponent: float) -> Result[Measured, UncertaintyError]:
        """Return self ** exponent for a real scalar exponent."""
        if not math.isfinite(exponent):
            return Err(UncertaintyError.InvalidExponent)
        if self.value == 0 and exponent < 1:
            return Err(UncertaintyError.DomainError)
        if self.value < 0 and exponent != int(exponent):
            return Err(UncertaintyError.DomainError)
        try:  # frob:ticket 01M6WJQ4CCMWZCF8NK30FYTGN8
            value = self.value**exponent
            partial = exponent * self.value ** (exponent - 1) if self.value != 0 else 0.0
        except (OverflowError, ZeroDivisionError):
            _log.warning("pow(%g) overflow on %g", exponent, self.value)
            return Err(UncertaintyError.DomainError)
        unit = units.power_unit(self.unit, exponent)
        if isinstance(unit, Err):
            return Err(unit.danger_err)
        return _derive([self], [partial], value, unit.danger_ok, f"pow({exponent:g})")

    def neg(self) -> Result[Measured, UncertaintyError]:
        """Return -self (same uncertainty, fully anti-correlated with self)."""
        return _derive([self], [-1.0], -self.value, self.unit, "neg")

    def __add__(self, other: Measured | float) -> Result[Measured, UncertaintyError]:
        """Operator form of `add`; returns a Result."""
        return self.add(other)

    def __radd__(self, other: float) -> Result[Measured, UncertaintyError]:
        """Reflected `add` for scalar + Measured."""
        return self.add(other)

    def __sub__(self, other: Measured | float) -> Result[Measured, UncertaintyError]:
        """Operator form of `sub`; returns a Result."""
        return self.sub(other)

    def __rsub__(self, other: float) -> Result[Measured, UncertaintyError]:
        """Reflected `sub` for scalar - Measured."""
        return self.neg().and_then(lambda n: n.add(other))

    def __mul__(self, other: Measured | float) -> Result[Measured, UncertaintyError]:
        """Operator form of `mul`; returns a Result."""
        return self.mul(other)

    def __rmul__(self, other: float) -> Result[Measured, UncertaintyError]:
        """Reflected `mul` for scalar * Measured."""
        return self.mul(other)

    def __truediv__(self, other: Measured | float) -> Result[Measured, UncertaintyError]:
        """Operator form of `div`; returns a Result."""
        return self.div(other)

    def __rtruediv__(self, other: float) -> Result[Measured, UncertaintyError]:
        """Reflected `div` for scalar / Measured."""
        return self.power(-1.0).and_then(lambda inv: inv.mul(other))

    def __pow__(self, exponent: float) -> Result[Measured, UncertaintyError]:
        """Operator form of `power`; returns a Result."""
        return self.power(exponent)

    def __neg__(self) -> Result[Measured, UncertaintyError]:
        """Operator form of `neg`; returns a Result."""
        return self.neg()


def _constant(value: float) -> Result[Measured, UncertaintyError]:
    """Wrap an exact dimensionless scalar as a zero-uncertainty Measured."""
    return Measured.create(
        float(value), 0.0, provenance=Provenance(source="constant"), registry=DEFAULT_REGISTRY
    )


def _as_measured(other: Measured | float) -> Result[Measured, UncertaintyError]:
    """Pass Measured through, wrap scalars as exact constants."""
    return Ok(other) if isinstance(other, Measured) else _constant(other)


def _additive(
    a: Measured, other: Measured | float, sign: float, name: str
) -> Result[Measured, UncertaintyError]:
    """Shared add/sub: check dimensions, then propagate partials (1, sign)."""
    b = _as_measured(other)
    if isinstance(b, Err):
        return b
    bm = b.danger_ok
    same = units.same_dimension(a.unit, bm.unit)
    if isinstance(same, Err):
        return Err(same.danger_err)
    if not same.danger_ok:
        _log.warning("%s: dimension mismatch %s vs %s", name, a.unit, bm.unit)
        return Err(UncertaintyError.DimensionMismatch)
    return _derive([a, bm], [1.0, sign], a.value + sign * bm.value, a.unit, name)


def _multiplicative(
    a: Measured, other: Measured | float, op: str, name: str
) -> Result[Measured, UncertaintyError]:
    """Shared mul/div with the product/quotient partials and combined units."""
    b = _as_measured(other)
    if isinstance(b, Err):
        return b
    bm = b.danger_ok
    unit = units.combine_units(a.unit, bm.unit, op)
    if isinstance(unit, Err):
        return Err(unit.danger_err)
    if op == "*":
        value, partials = a.value * bm.value, [bm.value, a.value]
    else:
        if bm.value == 0:
            _log.warning("div by zero")
            return Err(UncertaintyError.DomainError)
        value = a.value / bm.value
        partials = [
            1.0 / bm.value,
            -(a.value / bm.value) / bm.value,
        ]  # no ** : 1e-200**2 underflows to 0
    return _derive([a, bm], partials, value, unit.danger_ok, name)


def _derive(
    inputs: Sequence[Measured],
    partials: Sequence[float],
    value: float,
    unit: str,
    name: str,
    registry: CovarianceRegistry = DEFAULT_REGISTRY,
) -> Result[Measured, UncertaintyError]:
    """Build the derived Measured: RSS with full covariance, Welch-Satterthwaite dof, provenance."""
    if not (math.isfinite(value) and all(math.isfinite(p) for p in partials)):
        return Err(UncertaintyError.DomainError)
    contribs = [(abs(p) * m.std_unc, m.dof) for m, p in zip(inputs, partials, strict=True)]
    if not all(math.isfinite(u) for u, _ in contribs):  # frob:ticket 01M6WJQ4CCMWZCF8NK30FYTGN8
        _log.warning("%s: contribution overflow (tiny divisor?)", name)
        return Err(UncertaintyError.InvalidUncertainty)
    ident = uuid.uuid4().hex
    for m in inputs:
        if not registry.known(m.id):
            registry.register(m.id, m.std_unc**2)
    var = registry.register_derived(
        ident, [(m.id, p) for m, p in zip(inputs, partials, strict=True)]
    )
    if not math.isfinite(var):  # frob:ticket 01M6WJQ4CCMWZCF8NK30FYTGN8
        _log.warning("%s: variance overflow", name)
        return Err(UncertaintyError.InvalidUncertainty)
    dof = coverage.effective_dof(contribs).unwrap_or(math.inf)
    out = Measured(
        id=ident,
        value=value,
        std_unc=math.sqrt(var),
        unit=unit,
        dof=dof,
        provenance=Provenance(
            source="derived", derivation=name, parents=tuple(m.id for m in inputs)
        ),
    )
    _track(out, registry)
    _log.debug("derived %s via %s = %g +/- %g %s", ident, name, out.value, out.std_unc, unit)
    return Ok(out)
