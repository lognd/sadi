# Uncertainty: numeric and Monte Carlo fallbacks

Status: current

Code: python/sadi/uncertainty/numeric.py, montecarlo.py, and the dispatch in uncertain.py.
Neither module imports `sadi.store` or any web module, so Monte Carlo can run in the
`sadi.jobs` worker pool.

## Method selection

| `method=` | Behaviour |
|-----------|-----------|
| `"auto"` (default) | Analytic (sympy); on `Untraceable`/`NotDifferentiable` use numeric |
| `"analytic"` | Sympy only; failures are returned as `UncertainError` |
| `"numeric"` | Numeric partials, same full-covariance RSS `u^2 = J C J^T` |
| `"mc"` | Monte Carlo (`McConfig(n, seed, marginals, batch_size)`) |

## Numeric derivatives

Per partial: complex-step (step 1e-30 x scale, no cancellation) is tried first and accepted only
if it agrees with a coarse Ridders central difference (rtol 1e-4 plus ten error estimates).
This rejects silent wrong answers such as `np.abs`. Otherwise Ridders extrapolated central
differences are used, with step control (stop when the error estimate grows) and a convergence
requirement (relative error at most 1e-3, else `NumericError.NoConvergence`). Result:
`NumericGradient(value, gradient, methods, errors)`. Errors: `NumEvalFailed`, `NumNonFinite`,
`NoConvergence`. A step that underflows to zero (for example a 1e-300 argument) returns
`NumNonFinite` instead of dividing by zero.

## Monte Carlo

`McSampler.create(fn, means, cov, seed=, marginals=, dofs=, batch_size=)` or
`McSampler.from_measured(fn, args, registry, seed=)` (covariance from the registry).

- Correlated draws use a Gaussian copula (eigen-decomposition of the correlation matrix), so
  the full covariance is honoured. Marginals: `NORMAL`, `UNIFORM`, `TRIANGULAR`,
  `STUDENT_T` (needs dof > 2); each is scaled to the stated mean and sd. Non-normal marginals
  slightly attenuate the realised correlation.
- Output `McEstimate`: n, seed, mean, std, 95% interval (2.5/97.5 percentiles), se_mean, se_std.
- Vectorised evaluation by default; falls back to a row loop for branchy code.
- Seeded and reproducible. Batch k uses `SeedSequence(seed, spawn_key=(k,))`.
- Resumable: `run_to(total)` adds batches; refining 4096 -> 16384 -> 40000 gives results
  identical to a fresh run to the same total (totals round up to whole batches).
- Cancellable: `run_to(total, cancel)` polls `cancel()` before each batch and returns
  `Err(Cancelled)`, keeping finished batches so a later call resumes.
- Finite samples whose mean or sd overflow (outputs near 1e300) return `McNonFinite`, silently.
- Errors: `Cancelled`, `McNotMeasured`, `BadSize`, `BadCovariance`, `BadDistribution`,
  `McEvalFailed`, `McNonFinite`.

Caveats: the `Measured` returned by `method="mc"` carries no covariance links to its inputs.
Unit inference can fail when probing numpy functions with pint; pass `unit=` explicitly.

## Cross-check

`cross_check(estimates, rel_tol=0.05, k_sigma=4.0)` compares `MethodEstimate`s and reports a
`Disagreement` for value or std_unc when `|x-y| > rel_tol*max(|x|,|y|) + k_sigma*hypot(se_x, se_y)`.
`Uncertain.cross_check(*args)` runs analytic, numeric and MC and returns a `CrossCheck`
(`agree`, `findings`). Genuine nonlinearity (first-order vs MC sd) is flagged by design.

Cross-check of every lab formula: see [crosscheck](crosscheck.md).
