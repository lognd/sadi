# Uncertainty: @uncertain

Status: current

`from sadi.uncertainty import uncertain` (python/sadi/uncertainty/uncertain.py). Not named
`propagate`/`catching`, which typani exports (see [naming](naming.md)).

## Usage

```python
@uncertain
def area(w, h):
    return w * h

area(w_measured, h_measured)   # -> Result[Measured, UncertainError | UncertaintyError]
```

The function is written as plain math over its parameters. It is traced once with sympy
symbols (`symbolic.trace`), differentiated per parameter, and lambdified to numpy. Traces are
cached per function (`TRACE_CACHE`); the inferred result unit is cached per function and per
argument-unit tuple (`UNIT_CACHE`). Errors are never cached.

## Propagation

`u^2 = J C J^T` with `C` the full covariance of the argument Measured values from the
`CovarianceRegistry` (default `DEFAULT_REGISTRY`; pass `registry=` to isolate). Correlation
such as calibration slope vs intercept is honoured, and the result is registered so later
combinations keep their covariance. Dof come from Welch-Satterthwaite as for `Measured`
arithmetic.

## Introspection

All return `Result` (never raise): `.symbolic` (sympy expression), `.partials`
(dict name -> expression), `.latex` (formula, partials and the `J C J^T` rule),
`.sensitivities(*measured)` (numeric partials at the inputs).

## Units

Result unit: explicit `@uncertain(unit="N")`, otherwise inferred by running the function on pint
quantities (works for `+ - * / **`). Mixed dimensions give `MixedDimensions`. Functions using
sympy functions (`sin`, `exp`) cannot be unit-probed: pass `unit=`, or use only dimensionless
arguments.

## Errors (`UncertainError`)

`Untraceable` (e.g. `math.sin`; use sympy functions), `NotDifferentiable` (e.g. `floor`),
`NotMeasured`, `Arity`, `BadSignature` (varargs), `MixedDimensions`, `UnitNotInferred`,
`NonFiniteResult`. Untraceable and NotDifferentiable point to the numeric-derivative and
Monte Carlo fallbacks.

## Budget

`.budget(*measured)` ranks each input's share of the variance; see [budget](budget.md).

## Methods and fallbacks

`uncertain(fn, method=...)` takes `"auto"` (default), `"analytic"`, `"numeric"` or `"mc"`. Under
`"auto"` an `Untraceable` or `NotDifferentiable` analytic failure falls back to numeric
derivatives instead of returning the error; pass `method="analytic"` to keep the strict
behaviour. See [fallbacks](fallbacks.md).
