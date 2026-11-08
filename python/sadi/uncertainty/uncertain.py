"""The `@uncertain` decorator: sympy-traced partials, full-covariance RSS, Measured result.

`method=` selects the analytic (sympy), numeric-derivative or Monte Carlo path; see fallbacks.md.
"""

# frob:ticket 01M6W7R1RD3P97HFFDZ2NVD83Y

from __future__ import annotations

import functools
from collections.abc import Callable, Sequence
from typing import Literal, overload

import sympy
from pydantic import BaseModel, ConfigDict
from typani import Err, Ok, Result

from sadi.logging_setup import get_logger
from sadi.uncertainty import units
from sadi.uncertainty.budget import Budget, build_budget
from sadi.uncertainty.covariance import DEFAULT_REGISTRY, CovarianceRegistry
from sadi.uncertainty.errors import UncertaintyError
from sadi.uncertainty.measured import Measured, Provenance, _derive
from sadi.uncertainty.montecarlo import (
    CancelCheck,
    CrossCheck,
    Marginal,
    McEstimate,
    McSampler,
    MethodEstimate,
    MonteCarloError,
    cross_check,
    from_mc,
)
from sadi.uncertainty.numeric import NumericError, gradient
from sadi.uncertainty.symbolic import (
    TRACE_CACHE,
    UNIT_CACHE,
    Compiled,
    UncertainError,
    _param_names,
    evaluate,
    latex_derivation,
    output_unit,
    trace,
)

_log = get_logger(__name__)

AnyError = UncertainError | UncertaintyError | NumericError | MonteCarloError

Method = Literal["auto", "analytic", "numeric", "mc"]
_FALLBACK_TRIGGERS = (UncertainError.Untraceable, UncertainError.NotDifferentiable)


# frob:ticket 01M6W7R2A727G6H66B6FBSDE1R
class McConfig(BaseModel):
    """Monte Carlo settings for `method="mc"`: sample count, seed, marginals and batch size."""

    model_config = ConfigDict(frozen=True)

    n: int = 20000
    seed: int = 0
    marginals: tuple[Marginal, ...] | None = None
    batch_size: int = 4096


class Uncertain:
    """A plain-math function lifted to Measured arguments with automatic propagation."""

    def __init__(
        self,
        fn: Callable[..., object],
        unit: str | None = None,
        registry: CovarianceRegistry = DEFAULT_REGISTRY,
        method: Method = "auto",
        mc: McConfig | None = None,
    ) -> None:
        """Wrap `fn`; `unit` fixes the result unit, else it is inferred with pint.

        `method` is "analytic", "numeric", "mc" or "auto" (analytic, falling back to numeric
        derivatives when the function cannot be traced); `mc` configures Monte Carlo.
        """
        self._fn = fn
        self._unit = unit
        self._registry = registry
        self._method: Method = method
        self._mc = mc or McConfig()
        self.__name__ = getattr(fn, "__name__", "uncertain")
        self.__doc__ = fn.__doc__
        functools.update_wrapper(self, fn)

    def compiled(self) -> Result[Compiled, UncertainError]:
        """Return the cached trace (expression, partials, evaluator) of the function."""
        return TRACE_CACHE.get_or_compute(self._fn, lambda: trace(self._fn))

    @property
    def symbolic(self) -> Result[sympy.Basic, UncertainError]:
        """The traced sympy expression of the function."""
        return self.compiled().map(lambda c: c.expr)

    @property
    def partials(self) -> Result[dict[str, sympy.Basic], UncertainError]:
        """Symbolic partial derivatives keyed by parameter name."""
        return self.compiled().map(lambda c: dict(zip(c.names, c.partials, strict=True)))

    @property
    def latex(self) -> Result[str, UncertainError]:
        """LaTeX of the formula, its partials and the u^2 = J C J^T rule."""
        return self.compiled().map(latex_derivation)

    def sensitivities(self, *args: Measured) -> Result[dict[str, float], AnyError]:
        """Return the numeric partials df/dx_i evaluated at the argument values."""
        return (
            self._checked(args)
            .and_then(lambda c: self._eval(c, args))
            .map(lambda out: dict(zip(self._names(), out[1:], strict=True)))
        )

    # frob:ticket 01M6W7R2BS0R89GW39HM0XPX0J
    def budget(self, *args: Measured) -> Result[Budget, AnyError]:
        """Return the ranked per-input uncertainty budget at the argument values."""
        return self.sensitivities(*args).map(
            lambda sens: build_budget(
                self._names(), args, [sens[n] for n in self._names()], self._registry
            )
        )

    # frob:ticket 01M6W7R2A727G6H66B6FBSDE1R
    def __call__(self, *args: Measured) -> Result[Measured, AnyError]:
        """Evaluate at `args` and propagate uncertainty with the full covariance matrix."""
        if self._method == "mc":
            return self._call_mc(args)
        if self._method == "numeric":
            return self._call_numeric(args)
        result = self._call_analytic(args)
        if (
            self._method == "auto"
            and isinstance(result, Err)
            and result.danger_err in _FALLBACK_TRIGGERS
        ):
            _log.info("%s: analytic failed (%s); using numeric", self.__name__, result.danger_err)
            return self._call_numeric(args)
        return result

    # frob:ticket 01M6W7R2A727G6H66B6FBSDE1R
    def sampler(self, *args: Measured, seed: int | None = None) -> Result[McSampler, AnyError]:
        """Return a resumable Monte Carlo sampler over the full input covariance."""
        return McSampler.from_measured(
            self._fn,
            args,
            self._registry,
            seed=self._mc.seed if seed is None else seed,
            marginals=self._mc.marginals,
            batch_size=self._mc.batch_size,
        )

    # frob:ticket 01M6W7R2A727G6H66B6FBSDE1R
    def monte_carlo(
        self,
        *args: Measured,
        n: int | None = None,
        seed: int | None = None,
        cancel: CancelCheck | None = None,
    ) -> Result[McEstimate, AnyError]:
        """Run Monte Carlo to `n` samples; `cancel` is polled between batches."""
        sampler = self.sampler(*args, seed=seed)
        if isinstance(sampler, Err):
            return Err(sampler.danger_err)
        return sampler.danger_ok.run_to(self._mc.n if n is None else n, cancel)

    # frob:ticket 01M6W7R2A727G6H66B6FBSDE1R
    def cross_check(self, *args: Measured, rel_tol: float = 0.05) -> Result[CrossCheck, AnyError]:
        """Compare analytic, numeric and Monte Carlo (value, std_unc); flags disagreement."""
        entries: list[MethodEstimate] = []
        analytic = self._call_analytic(args)
        if isinstance(analytic, Ok):
            entries.append(_as_estimate("analytic", analytic.danger_ok))
        elif analytic.danger_err not in _FALLBACK_TRIGGERS:
            return Err(analytic.danger_err)
        numeric = self._call_numeric(args)
        if isinstance(numeric, Err):
            return Err(numeric.danger_err)
        entries.append(_as_estimate("numeric", numeric.danger_ok))
        mc = self.monte_carlo(*args)
        if isinstance(mc, Err):
            return Err(mc.danger_err)
        entries.append(from_mc(mc.danger_ok))
        report = cross_check(entries, rel_tol=rel_tol)
        _log.info("%s cross-check agree=%s", self.__name__, report.agree)
        return Ok(report)

    def _call_analytic(self, args: Sequence[Measured]) -> Result[Measured, AnyError]:
        """Sympy-traced path: exact partials, full-covariance RSS."""
        compiled = self._checked(args)
        if isinstance(compiled, Err):
            return Err(compiled.danger_err)
        values = self._eval(compiled.danger_ok, args)
        if isinstance(values, Err):
            return Err(values.danger_err)
        unit = self._result_unit(args)
        if isinstance(unit, Err):
            return Err(unit.danger_err)
        out = values.danger_ok
        _log.debug("%s -> %g", self.__name__, out[0])
        return _derive(
            list(args),
            out[1:],
            out[0],
            unit.danger_ok,
            f"uncertain({self.__name__})",
            self._registry,
        )

    def _check_plain(self, args: Sequence[object]) -> Result[None, AnyError]:
        """Validate Measured arguments and arity without needing a sympy trace."""
        if not all(isinstance(a, Measured) for a in args):
            return Err(UncertainError.NotMeasured)
        names = _param_names(self._fn)
        if isinstance(names, Err):
            return Err(names.danger_err)
        if len(names.danger_ok) != len(args):
            return Err(UncertainError.Arity)
        return Ok(None)

    def _call_numeric(self, args: Sequence[Measured]) -> Result[Measured, AnyError]:
        """Numeric-derivative path: complex-step or adaptive central differences."""
        checked = self._check_plain(args)
        if isinstance(checked, Err):
            return Err(checked.danger_err)
        grad = gradient(self._fn, [a.value for a in args])
        if isinstance(grad, Err):
            return Err(grad.danger_err)
        unit = self._result_unit(args)
        if isinstance(unit, Err):
            return Err(unit.danger_err)
        g = grad.danger_ok
        _log.debug("%s numeric -> %g via %s", self.__name__, g.value, g.methods)
        return _derive(
            list(args),
            g.gradient,
            g.value,
            unit.danger_ok,
            f"uncertain-numeric({self.__name__})",
            self._registry,
        )

    def _call_mc(self, args: Sequence[Measured]) -> Result[Measured, AnyError]:
        """Monte Carlo path: result is the sample mean and sd (no covariance with inputs)."""
        checked = self._check_plain(args)
        if isinstance(checked, Err):
            return Err(checked.danger_err)
        est = self.monte_carlo(*args)
        if isinstance(est, Err):
            return Err(est.danger_err)
        unit = self._result_unit(args)
        if isinstance(unit, Err):
            return Err(unit.danger_err)
        e = est.danger_ok
        return Measured.create(
            e.mean,
            e.std,
            unit.danger_ok,
            provenance=Provenance(
                source="derived",
                derivation=f"uncertain-mc({self.__name__}, n={e.n}, seed={e.seed})",
                parents=tuple(a.id for a in args),
            ),
            registry=self._registry,
        )

    def _names(self) -> tuple[str, ...]:
        """Parameter names of the traced function (trace is already cached)."""
        return self.compiled().unwrap().names

    def _checked(self, args: Sequence[object]) -> Result[Compiled, UncertainError]:
        """Validate argument types and arity against the cached trace."""
        if not all(isinstance(a, Measured) for a in args):
            _log.warning("%s: non-Measured argument", self.__name__)
            return Err(UncertainError.NotMeasured)
        compiled = self.compiled()
        if isinstance(compiled, Ok) and len(args) != len(compiled.danger_ok.names):
            _log.warning("%s: arity %d", self.__name__, len(args))
            return Err(UncertainError.Arity)
        return compiled

    def _eval(self, c: Compiled, args: Sequence[Measured]) -> Result[list[float], UncertainError]:
        """Evaluate value and partials at the Measured values."""
        return evaluate(c, [a.value for a in args])

    def _result_unit(self, args: Sequence[Measured]) -> Result[str, UncertainError]:
        """Resolve the result unit: explicit, else inferred and cached per argument units."""
        if self._unit is not None:
            parsed = units.parse_unit(self._unit)
            if isinstance(parsed, Err):
                return Err(UncertainError.UnitNotInferred)
            return Ok(self._unit)
        arg_units = tuple(a.unit for a in args)
        return UNIT_CACHE.get_or_compute(
            (self._fn, arg_units), lambda: output_unit(self._fn, arg_units)
        )


@overload
def uncertain(
    fn: Callable[..., object],
    *,
    unit: str | None = None,
    registry: CovarianceRegistry = DEFAULT_REGISTRY,
    method: Method = "auto",
    mc: McConfig | None = None,
) -> Uncertain:
    """Decorate `fn` directly."""
    ...


@overload
def uncertain(
    fn: None = None,
    *,
    unit: str | None = None,
    registry: CovarianceRegistry = DEFAULT_REGISTRY,
    method: Method = "auto",
    mc: McConfig | None = None,
) -> Callable[[Callable[..., object]], Uncertain]:
    """Return a decorator configured with `unit`, `registry`, `method` and `mc`."""
    ...


def uncertain(
    fn: Callable[..., object] | None = None,
    *,
    unit: str | None = None,
    registry: CovarianceRegistry = DEFAULT_REGISTRY,
    method: Method = "auto",
    mc: McConfig | None = None,
) -> Uncertain | Callable[[Callable[..., object]], Uncertain]:
    """Decorate a plain-math function so it accepts Measured and returns a Result[Measured]."""
    if fn is None:
        _log.debug("uncertain: decorator factory unit=%s", unit)
        return lambda f: Uncertain(f, unit, registry, method, mc)
    return Uncertain(fn, unit, registry, method, mc)


def _as_estimate(method: str, m: Measured) -> MethodEstimate:
    """View a propagated Measured as an exact (no sampling error) cross-check entry."""
    return MethodEstimate(method=method, value=m.value, std_unc=m.std_unc)
