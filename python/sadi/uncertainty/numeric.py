"""Numeric-derivative fallback: complex-step where valid, else adaptive central differences."""

# frob:ticket 01M6W7R2A727G6H66B6FBSDE1R

from __future__ import annotations

import math
from collections.abc import Callable, Sequence

import numpy as np
from pydantic import BaseModel, ConfigDict
from typani import Err, ErrorSet, Ok, Result

from sadi.logging_setup import get_logger

_log = get_logger(__name__)

# Complex-step increment relative to the argument scale; no subtractive cancellation.
_CS_STEP = 1e-30
# Complex-step must agree with a coarse central difference to this relative tolerance.
_CS_AGREE_RTOL = 1e-4
# Ridders extrapolation: step shrink factor and maximum tableau depth.
_CON = 1.4
_DEPTH = 12
# Largest acceptable relative error estimate for a central-difference derivative.
_MAX_REL_ERR = 1e-3
# Floor on the default initial step so 2*h and h/_CON^k stay normal floats for subnormal x.
_MIN_STEP = 1e-100


class NumericError(ErrorSet):
    """Failure modes of the numeric-derivative path; the description says what to do next."""

    NumEvalFailed = (
        "Function raised when evaluated at the inputs; check the domain or use method='mc'"
    )
    NumNonFinite = "Function is non-finite at or near the inputs; move away from the singularity"
    NoConvergence = (
        "Finite differences did not converge (kink, jump or noise); use method='mc' instead"
    )


class NumericGradient(BaseModel):
    """Value and numeric partials of a function with the technique and error bound per partial."""

    model_config = ConfigDict(frozen=True)

    value: float
    gradient: tuple[float, ...]
    methods: tuple[str, ...]
    errors: tuple[float, ...]


def _scalar(v: object) -> Result[complex, NumericError]:
    """Coerce a function output to a Python complex; EvalFailed if it is not a number."""
    return Result.catch(
        lambda: complex(np.asarray(v).reshape(())[()]),
        Exception,
        on_error=lambda exc: NumericError.NumEvalFailed,
    )


def _real_call(fn: Callable[..., object], xs: Sequence[float]) -> Result[float, NumericError]:
    """Evaluate `fn` at real `xs`; EvalFailed on exception, NonFinite on nan/inf/complex."""

    def run() -> object:
        with np.errstate(all="ignore"):
            return fn(*xs)

    out = Result.catch(run, Exception, on_error=lambda exc: NumericError.NumEvalFailed)
    if isinstance(out, Err):
        return Err(out.danger_err)
    z = _scalar(out.danger_ok)
    if isinstance(z, Err):
        return Err(z.danger_err)
    if not (math.isfinite(z.danger_ok.real) and z.danger_ok.imag == 0.0):
        return Err(NumericError.NumNonFinite)
    return Ok(z.danger_ok.real)


def _scale(x: float) -> float:
    """Characteristic magnitude of an argument used to size steps (1.0 only when x == 0).

    frob:ticket 01M6WJQ4A9Q9MTK0XQQSJ9VQC9 - a floor of 1.0 made steps cross the pole of a/x for |x| < 1.
    """
    return abs(x) if x != 0.0 else 1.0


def complex_step(
    fn: Callable[..., object], xs: Sequence[float], i: int
) -> Result[float, NumericError]:
    """Return df/dx_i as Im f(x + i h e_i)/h; fails if `fn` cannot take complex input."""
    h = _CS_STEP * _scale(xs[i])
    if h <= 0.0 or not math.isfinite(h):
        # frob:ticket 01M6WK9WBZ01A4XA77S5T2MJV9
        # 1e-30 * 1e-300 underflows to 0, so Im f / h would raise.
        _log.warning("complex-step increment underflowed for x=%g", xs[i])
        return Err(NumericError.NumNonFinite)
    zs: list[complex] = [complex(x) for x in xs]
    zs[i] = complex(xs[i], h)

    def run() -> object:
        with np.errstate(all="ignore"):
            return fn(*zs)

    out = Result.catch(run, Exception, on_error=lambda exc: NumericError.NumEvalFailed)
    if isinstance(out, Err):
        return Err(out.danger_err)
    z = _scalar(out.danger_ok)
    if isinstance(z, Err):
        return Err(z.danger_err)
    d = z.danger_ok.imag / h
    if not math.isfinite(d):
        return Err(NumericError.NumNonFinite)
    return Ok(d)


def _shifted(xs: Sequence[float], i: int, delta: float) -> list[float]:
    """Copy of `xs` with component i moved by `delta`."""
    out = list(xs)
    out[i] += delta
    return out


def central_difference(
    fn: Callable[..., object], xs: Sequence[float], i: int, h0: float | None = None
) -> Result[tuple[float, float], NumericError]:
    """Return (df/dx_i, error estimate) by Ridders extrapolated central differences.

    The step starts at `h0` (default 1e-2 of the argument scale) and shrinks by a constant
    factor; iteration stops when the error estimate starts to grow (step control).
    """
    # frob:ticket 01M6WRR08HNAKHCT71WW0VNNSP
    h = h0 if h0 is not None else max(1e-2 * _scale(xs[i]), _MIN_STEP)
    if h == 0.0 or not math.isfinite(2.0 * h):
        _log.warning("central difference step %g is not representable", h)
        return Err(NumericError.NoConvergence)
    tab: list[list[float]] = [[0.0] * _DEPTH for _ in range(_DEPTH)]
    best, best_err = 0.0, math.inf
    for k in range(_DEPTH):
        plus = _real_call(fn, _shifted(xs, i, h))
        minus = _real_call(fn, _shifted(xs, i, -h))
        if isinstance(plus, Err):
            failure = plus.danger_err
        elif isinstance(minus, Err):
            failure = minus.danger_err
        else:
            failure = None
        if failure is not None:
            _log.warning("central difference eval failed at step %g: %s", h, failure)
            if k == 0:
                return Err(failure)
            break
        tab[0][k] = (plus.unwrap() - minus.unwrap()) / (2.0 * h)
        fac = _CON * _CON
        for j in range(1, k + 1):
            tab[j][k] = (tab[j - 1][k] * fac - tab[j - 1][k - 1]) / (fac - 1.0)
            fac *= _CON * _CON
            err = max(abs(tab[j][k] - tab[j - 1][k]), abs(tab[j][k] - tab[j - 1][k - 1]))
            if err <= best_err:
                best, best_err = tab[j][k], err
        if k >= 1 and abs(tab[k][k] - tab[k - 1][k - 1]) >= 2.0 * best_err:
            break
        h /= _CON
    f0 = _real_call(fn, xs)
    ref = max(abs(best), abs(f0.unwrap_or(0.0)) / _scale(xs[i]), 1e-9)
    if not math.isfinite(best_err) or best_err > _MAX_REL_ERR * ref:
        _log.warning("central difference did not converge: d=%g err=%g", best, best_err)
        return Err(NumericError.NoConvergence)
    return Ok((best, best_err))


def _derivative(
    fn: Callable[..., object], xs: Sequence[float], i: int
) -> Result[tuple[float, str, float], NumericError]:
    """Partial i by complex step when it agrees with a central difference, else by Ridders."""
    cs = complex_step(fn, xs, i)
    cd = central_difference(fn, xs, i)
    if isinstance(cs, Ok) and isinstance(cd, Ok):
        d_cs, (d_cd, err) = cs.danger_ok, cd.danger_ok
        if abs(d_cs - d_cd) <= _CS_AGREE_RTOL * max(abs(d_cs), abs(d_cd), 1e-12) + 10.0 * err:
            _log.debug("partial %d: complex-step %g", i, d_cs)
            return Ok((d_cs, "complex", 0.0))
        _log.info("partial %d: complex-step %g disagrees with central %g", i, d_cs, d_cd)
    if isinstance(cd, Err):
        return Err(cd.danger_err)
    _log.debug("partial %d: central %g +/- %g", i, cd.danger_ok[0], cd.danger_ok[1])
    return Ok((cd.danger_ok[0], "central", cd.danger_ok[1]))


def gradient(
    fn: Callable[..., object], xs: Sequence[float]
) -> Result[NumericGradient, NumericError]:
    """Return f(xs) and all partials, choosing complex-step or adaptive central differences."""
    f0 = _real_call(fn, xs)
    if isinstance(f0, Err):
        return Err(f0.danger_err)
    parts: list[tuple[float, str, float]] = []
    for i in range(len(xs)):
        d = _derivative(fn, xs, i)
        if isinstance(d, Err):
            return Err(d.danger_err)
        parts.append(d.danger_ok)
    _log.info("numeric gradient of %s: %s", getattr(fn, "__name__", fn), [p[1] for p in parts])
    return Ok(
        NumericGradient(
            value=f0.danger_ok,
            gradient=tuple(p[0] for p in parts),
            methods=tuple(p[1] for p in parts),
            errors=tuple(p[2] for p in parts),
        )
    )
