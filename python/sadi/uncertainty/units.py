"""Pint-backed unit handling: parse, dimension check and conversion to SI base units."""

# frob:ticket 01M6W7R155JD0XGVXHDSP19B1H

from __future__ import annotations

import pint
from typani import Err, Ok, Result

from sadi.logging_setup import get_logger
from sadi.uncertainty.errors import UncertaintyError

_log = get_logger(__name__)

UREG = pint.UnitRegistry()
DIMENSIONLESS = "dimensionless"


def parse_unit(text: str) -> Result[pint.Unit, UncertaintyError]:
    """Parse `text` into a pint Unit, or UnknownUnit."""
    parsed = Result.catch(
        lambda: UREG.Unit(text or DIMENSIONLESS),
        Exception,
        on_error=lambda exc: UncertaintyError.UnknownUnit,
    )
    if isinstance(parsed, Err):
        _log.warning("unknown unit %r", text)
    return parsed


def to_si(
    value: float, std_unc: float, unit: str
) -> Result[tuple[float, float, str], UncertaintyError]:
    """Convert value and standard uncertainty from `unit` to SI base units.

    The uncertainty is converted as a difference so offset units (degC) work.
    """
    parsed = parse_unit(unit)
    if isinstance(parsed, Err):
        return Err(parsed.danger_err)
    parsed_unit = parsed.danger_ok
    base = Result.catch(
        lambda: (
            UREG.Quantity(value, parsed_unit).to_base_units(),
            UREG.Quantity(value + std_unc, parsed_unit).to_base_units(),
        ),
        Exception,
        on_error=lambda exc: UncertaintyError.DimensionMismatch,
    )
    if isinstance(base, Err):
        return Err(base.danger_err)
    centre, shifted = base.danger_ok
    si_unit = f"{centre.units:~}" if not centre.dimensionless else DIMENSIONLESS
    out = (
        float(centre.magnitude),
        abs(float(shifted.magnitude) - float(centre.magnitude)),
        si_unit,
    )
    _log.debug("to_si %r %s -> %r", value, unit, out)
    return Ok(out)


def same_dimension(a: str, b: str) -> Result[bool, UncertaintyError]:
    """Return Ok(True) if units `a` and `b` share a dimensionality, else Ok(False)."""
    pa, pb = parse_unit(a), parse_unit(b)
    if isinstance(pa, Err):
        return Err(pa.danger_err)
    if isinstance(pb, Err):
        return Err(pb.danger_err)
    return Ok(pa.danger_ok.dimensionality == pb.danger_ok.dimensionality)


def combine_units(a: str, b: str, op: str) -> Result[str, UncertaintyError]:
    """Return the SI unit string of `a * b` (op '*') or `a / b` (op '/')."""
    pa, pb = parse_unit(a), parse_unit(b)
    if isinstance(pa, Err):
        return Err(pa.danger_err)
    if isinstance(pb, Err):
        return Err(pb.danger_err)
    prod = pa.danger_ok * pb.danger_ok if op == "*" else pa.danger_ok / pb.danger_ok
    return Ok(_unit_str(prod))


def power_unit(a: str, exponent: float) -> Result[str, UncertaintyError]:
    """Return the unit string of `a ** exponent`, or an error if `a` is unknown."""
    pa = parse_unit(a)
    if isinstance(pa, Err):
        return Err(pa.danger_err)
    return Ok(_unit_str(pa.danger_ok**exponent))


def _unit_str(unit: pint.Unit) -> str:
    """Render a pint Unit as a parseable string, 'dimensionless' when empty."""
    text = f"{unit:~}"
    return text or DIMENSIONLESS
