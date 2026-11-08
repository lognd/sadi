"""Display formatting: significant-figure rounding, SI prefixes and plain-language confidence.

Class rule (docs/domain.md): results to 3 s.f., uncertainties to 2 s.f. The counts are
configuration (open question Q13). Inputs are SI; conversion to prefixed units happens here.
"""

# frob:ticket 01M6W7R1HWQMSEX38TQM27Y4NY

from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field
from typani import Err, Ok, Result

from sadi.core.errors import ComputeCode, ComputeError, InputCode, InputError
from sadi.core.models import Quantity
from sadi.logging_setup import get_logger

_log = get_logger(__name__)

#: SI prefix symbols by decimal exponent (multiples of 3); micro is ASCII "u".
SI_PREFIXES: dict[int, str] = {
    -24: "y", -21: "z", -18: "a", -15: "f", -12: "p", -9: "n", -6: "u", -3: "m",
    0: "", 3: "k", 6: "M", 9: "G", 12: "T", 15: "P", 18: "E", 21: "Z", 24: "Y",
}  # fmt: skip

#: Units whose symbol may take an SI prefix on the front (kg is shown as g + prefix).
_PREFIXABLE: frozenset[str] = frozenset({"m", "g", "s", "N", "Pa", "V", "m/V", "m/s", "V/s"})

#: Engineering values with exponent in [-3, 6) stay unscaled when the unit has no prefix.
_PLAIN_RANGE = range(-3, 6)


class Notation(StrEnum):
    """Exponent style: engineering (multiples of 3, SI prefix) or scientific (one leading digit)."""

    ENGINEERING = "engineering"
    SCIENTIFIC = "scientific"


class FormatConfig(BaseModel):
    """Significant-figure counts and notation; defaults are the class rule (3 / 2)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    result_sf: int = Field(default=3, ge=1, le=15)
    uncertainty_sf: int = Field(default=2, ge=1, le=15)
    notation: Notation = Notation.ENGINEERING


DEFAULT_CONFIG = FormatConfig()


def round_sig(x: Decimal, sf: int) -> Decimal:
    """Round `x` half-up to `sf` significant figures, re-rounding once if a carry adds a digit."""
    if x == 0:
        return Decimal(0)
    exp = x.adjusted()
    out = x.quantize(Decimal(1).scaleb(exp - sf + 1), rounding=ROUND_HALF_UP)
    if out.adjusted() > exp:  # 9.996 -> 10.00: keep exactly sf digits (10.0)
        out = x.quantize(Decimal(1).scaleb(out.adjusted() - sf + 1), rounding=ROUND_HALF_UP)
        _log.debug("carry while rounding %s to %d s.f.", x, sf)
    return out


def _plain(x: Decimal) -> str:
    """Render a rounded Decimal in positional notation, keeping significant trailing zeros."""
    if x == 0:
        return "0"
    return format(x, "f")


def _dec(x: float) -> Decimal:
    """Exact-as-printed Decimal of a float (shortest repr), with -0.0 folded to 0."""
    return Decimal(0) if x == 0 else Decimal(repr(x))


def _check(value: float, u: float) -> ComputeError | InputError | None:
    """Return the error for a non-finite value/u or negative u, else None."""
    if not (math.isfinite(value) and math.isfinite(u)):
        _log.warning("non-finite input value=%r u=%r", value, u)
        return ComputeError(code=ComputeCode.NOT_FINITE, detail=f"value={value!r} u={u!r}")
    if u < 0:
        _log.warning("negative uncertainty %r", u)
        return InputError(code=InputCode.OUT_OF_RANGE, detail=f"uncertainty {u!r} < 0")
    return None


def format_result(
    value: float,
    u: float,
    unit: str = "1",
    config: FormatConfig = DEFAULT_CONFIG,
) -> Result[str, ComputeError | InputError]:
    """Format an SI value and its 95 % uncertainty as 'v +/- U unit' per the class rule.

    Value gets `result_sf` s.f., U gets `uncertainty_sf` s.f. (even with a leading 1), both
    in the shared scale of the value (U in the value's scale if the value is 0). A rounding
    carry (0.0996 -> 0.10) keeps the full s.f. count. Exactly 0 prints as "0".
    """
    bad = _check(value, u)
    if bad is not None:
        return Err(bad)
    v, du = _dec(value), _dec(u)
    kg = unit == "kg" and config.notation is Notation.ENGINEERING
    base = "g" if kg else unit
    offset = 3 if kg else 0  # kg -> g
    ref = round_sig((v if v != 0 else du).scaleb(offset), config.result_sf)
    mag = ref.adjusted() if ref != 0 else 0
    if config.notation is Notation.SCIENTIFIC:
        exp = mag
        prefix = ""
    else:
        exp = mag // 3 * 3
        if base in _PREFIXABLE:
            exp = max(-24, min(24, exp))
            prefix = SI_PREFIXES[exp]
        else:
            if exp in _PLAIN_RANGE:
                exp = 0
            prefix = ""
    body = (
        f"{_plain(round_sig(v.scaleb(offset - exp), config.result_sf))}"
        f" +/- {_plain(round_sig(du.scaleb(offset - exp), config.uncertainty_sf))}"
    )
    show_exp = (
        exp != 0
        and not prefix
        and not (base in _PREFIXABLE and config.notation is Notation.ENGINEERING)
    )
    if show_exp:
        body = f"({body})e{exp:+d}"
    suffix = "" if base == "1" else f" {prefix}{base}"
    _log.debug("format_result %r +/- %r %s -> %s%s", value, u, unit, body, suffix)
    return Ok(body + suffix)


def format_quantity(
    q: Quantity, config: FormatConfig = DEFAULT_CONFIG
) -> Result[str, ComputeError | InputError]:
    """Format a Quantity (value, 95 % uncertainty, SI unit) with `format_result`."""
    return format_result(q.value, q.standard_uncertainty, q.unit, config)


def plain_language_confidence(
    value: float,
    u95: float,
    target: float,
    label: str = "E",
    config: FormatConfig = DEFAULT_CONFIG,
) -> Result[str, ComputeError | InputError]:
    """Return a one-line readout of relative 95 % uncertainty versus a relative `target`.

    `target` is a fraction (0.05 for 5 %). Reached means the displayed percentage (rounded
    to `uncertainty_sf` s.f.) is <= the target, so the sentence never contradicts itself.
    """
    bad = _check(value, u95)
    if bad is not None:
        return Err(bad)
    if not (math.isfinite(target) and target > 0):
        _log.warning("bad target %r", target)
        return Err(InputError(code=InputCode.OUT_OF_RANGE, detail=f"target {target!r} must be > 0"))
    if value == 0:
        _log.warning("relative uncertainty undefined for value 0")
        return Err(ComputeError(code=ComputeCode.DEGENERATE, detail="value is 0"))
    shown = round_sig(_dec(abs(u95 / value)) * 100, config.uncertainty_sf)
    goal = _dec(target) * 100
    reached = shown <= goal
    text = (
        f"{label} is known to within {_plain(shown)} % at 95 % confidence; "
        f"target {format(goal.normalize(), 'f')} % {'reached' if reached else 'not reached'}"
    )
    _log.info("confidence %s: reached=%s", text, reached)
    return Ok(text)
