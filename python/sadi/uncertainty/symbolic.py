"""Sympy tracing of plain-math functions: expression, partials, lambdified evaluators, units."""

# frob:ticket 01M6W7R1RD3P97HFFDZ2NVD83Y

from __future__ import annotations

import inspect
import math
from collections.abc import Callable, Sequence

import numpy as np
import pint
import sympy
from pydantic import BaseModel, ConfigDict
from typani import Err, ErrorSet, Ok, Result

from sadi.logging_setup import get_logger
from sadi.uncertainty import units
from sadi.uncertainty.cache import KeyedCache

_log = get_logger(__name__)

Evaluator = Callable[..., list[float]]


class UncertainError(ErrorSet):
    """Failure modes of `@uncertain`; the description names the fallback to use."""

    Untraceable = (
        "Function cannot be traced with sympy symbols; use plain arithmetic or sympy functions"
        " (not math.*), or fall back to the numeric-derivative or Monte Carlo path"
    )
    NotDifferentiable = (
        "Function has no closed-form derivative; fall back to the numeric-derivative"
        " or Monte Carlo path"
    )
    NotMeasured = "Every argument must be a Measured; wrap raw numbers with Measured.create"
    Arity = "Wrong number of arguments; pass one Measured per function parameter"
    BadSignature = "Only plain positional parameters are supported (no *args/**kwargs)"
    MixedDimensions = "Function mixes incompatible dimensions; convert inputs to match"
    UnitNotInferred = "Result unit cannot be inferred; pass unit='...' to @uncertain"
    NonFiniteResult = "Function or a partial is undefined or non-finite at these inputs"


class Compiled(BaseModel):
    """A traced function: symbols, expression, partials and numeric evaluators."""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    names: tuple[str, ...]
    symbols: tuple[sympy.Symbol, ...]
    expr: sympy.Basic
    partials: tuple[sympy.Basic, ...]
    evaluator: Evaluator


def trace(fn: Callable[..., object]) -> Result[Compiled, UncertainError]:
    """Trace `fn` with sympy symbols, differentiate, and lambdify value plus partials."""
    names = _param_names(fn)
    if isinstance(names, Err):
        return Err(names.danger_err)
    syms = tuple(sympy.Symbol(n, real=True) for n in names.danger_ok)
    traced = Result.catch(
        lambda: sympy.sympify(fn(*syms)),
        Exception,
        on_error=lambda exc: UncertainError.Untraceable,
    )
    if isinstance(traced, Err):
        _log.warning("trace failed for %s", getattr(fn, "__name__", fn))
        return Err(traced.danger_err)
    expr = traced.danger_ok
    if not isinstance(expr, sympy.Basic):
        return Err(UncertainError.Untraceable)
    diffs = Result.catch(
        lambda: tuple(sympy.diff(expr, s) for s in syms),
        Exception,
        on_error=lambda exc: UncertainError.NotDifferentiable,
    )
    if isinstance(diffs, Err):
        return Err(diffs.danger_err)
    partials = diffs.danger_ok
    if any(p.has(sympy.Derivative, sympy.Subs) for p in partials):
        _log.warning("unresolved derivative for %s", getattr(fn, "__name__", fn))
        return Err(UncertainError.NotDifferentiable)
    lam = Result.catch(
        lambda: sympy.lambdify(syms, [expr, *partials], modules="numpy"),
        Exception,
        on_error=lambda exc: UncertainError.Untraceable,
    )
    if isinstance(lam, Err):
        return Err(lam.danger_err)
    _log.info("traced %s: %s", getattr(fn, "__name__", fn), expr)
    return Ok(
        Compiled(
            names=names.danger_ok,
            symbols=syms,
            expr=expr,
            partials=partials,
            evaluator=lam.danger_ok,
        )
    )


def evaluate(compiled: Compiled, values: Sequence[float]) -> Result[list[float], UncertainError]:
    """Evaluate [f, df/dx_1, ...] at `values`; DomainError if anything is non-finite."""

    def run() -> list[float]:
        with np.errstate(all="ignore"):
            return [float(v) for v in compiled.evaluator(*values)]

    out = Result.catch(run, Exception, on_error=lambda exc: UncertainError.NonFiniteResult)
    if isinstance(out, Err):
        _log.warning("evaluation raised at %s", list(values))
        return Err(out.danger_err)
    if not all(math.isfinite(v) for v in out.danger_ok):
        _log.warning("non-finite result at %s", list(values))
        return Err(UncertainError.NonFiniteResult)
    return Ok(out.danger_ok)


def output_unit(fn: Callable[..., object], arg_units: Sequence[str]) -> Result[str, UncertainError]:
    """Infer the result unit by running `fn` on pint quantities; UnknownUnit if impossible."""
    parsed = [units.parse_unit(u) for u in arg_units]
    probes = []
    for i, p in enumerate(parsed):
        if isinstance(p, Err):
            return Err(UncertainError.UnitNotInferred)
        probes.append(units.UREG.Quantity(1.0 + 0.37 * (i + 1), p.danger_ok))
    probed = Result.catch(
        lambda: fn(*probes),
        Exception,
        on_error=lambda exc: (
            UncertainError.MixedDimensions
            if isinstance(exc, pint.DimensionalityError)
            else UncertainError.UnitNotInferred
        ),
    )
    if isinstance(probed, Err) and probed.danger_err is UncertainError.MixedDimensions:
        _log.warning("dimension mismatch inside function")
        return Err(UncertainError.MixedDimensions)
    res = probed.ok
    if isinstance(res, pint.Quantity):
        return Ok(f"{res.units:~}" if not res.dimensionless else units.DIMENSIONLESS)
    if all(u == units.DIMENSIONLESS for u in arg_units):
        return Ok(units.DIMENSIONLESS)
    _log.warning("cannot infer unit for %s", arg_units)
    return Err(UncertainError.UnitNotInferred)


def latex_derivation(compiled: Compiled) -> str:
    """Render the formula, each partial and the u^2 = J C J^T rule as LaTeX."""
    lines = [rf"y = {sympy.latex(compiled.expr)}"]
    for s, p in zip(compiled.symbols, compiled.partials, strict=True):
        lines.append(rf"\frac{{\partial y}}{{\partial {sympy.latex(s)}}} = {sympy.latex(p)}")
    lines.append(
        r"u_y^2 = \sum_i \sum_j \frac{\partial y}{\partial x_i}"
        r"\frac{\partial y}{\partial x_j}\,\mathrm{cov}(x_i, x_j)"
    )
    body = " \\\\\n".join(lines)
    return "\\begin{aligned}\n" + body + "\n\\end{aligned}"


def _param_names(fn: Callable[..., object]) -> Result[tuple[str, ...], UncertainError]:
    """Return the parameter names of `fn` if all are plain positional."""
    sig = Result.catch(
        lambda: inspect.signature(fn), Exception, on_error=lambda exc: UncertainError.BadSignature
    )
    if isinstance(sig, Err):
        return Err(sig.danger_err)
    params = list(sig.danger_ok.parameters.values())
    ok_kinds = (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    if any(p.kind not in ok_kinds for p in params):
        return Err(UncertainError.BadSignature)
    return Ok(tuple(p.name for p in params))


TRACE_CACHE: KeyedCache[Callable[..., object], Compiled, UncertainError] = KeyedCache("trace")
UNIT_CACHE: KeyedCache[tuple[Callable[..., object], tuple[str, ...]], str, UncertainError] = (
    KeyedCache("unit")
)
