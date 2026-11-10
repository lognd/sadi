# Weight-plan error propagation

`sadi.labs.lctt.propagate.propagate` turns one LCTT hang sequence into
stress, strain, Young's modulus and yield stress, each with a standard
uncertainty, a 95 percent interval and a per-input contribution
[budget](budget.md).

## One code path

Planned hangs (predictions) and captured data use the same function and
the same `PropagationInputs`. Only the voltages differ: a plan supplies
predicted voltages with their expected uncertainty, a capture supplies
measured ones.

## Inputs

- `inventory`: weight masses, each a `Measured`. A `Hang` lists indices
  into it, in hang order.
- `hanger`, `diameter`, `l0`, `slope`, `tare`: `Measured` values.
- `hangs`: one `Hang` per step, with its `voltage`.
- `window`: first and last hang index used for the chord modulus
  (default: all hangs). `offset`: yield strain offset (default 0.002).

## Outputs

`PropagationResult` holds `stress`, `strain`, `modulus` and
`yield_stress` as `Quantity` models: value, `std_unc`, `dof`, `k95`,
`low95`, `high95`, a `budget` and an optional Monte Carlo summary.
Stress and strain are per hang; modulus and yield are single values.

## Method

The GUM first-order result uses numeric sensitivities, the budget over
every input with a nonzero sensitivity, Welch-Satterthwaite effective
degrees of freedom and a Student-t interval. Pass `mc_n` to also run a
seeded Monte Carlo (`seed`, default `DEFAULT_MC_SEED`) for comparison.
Budget contributions sum to the total variance.

## Correlation

Covariances are read from the `registry` argument (default
`DEFAULT_REGISTRY`). Set a correlation between inputs that share a
calibration, for example slope and tare, before calling. Note tare
cancels in a chord modulus, so its correlation shows up in strain.

## Notes and errors

With fewer than two hangs, modulus and yield are `None` with a note. If
the curve never crosses the offset line, yield is `None` with a note.
Invalid inputs return `Err(PropagateError.*)`: `NoHangs`,
`BadWeightIndex`, `BadWindow`, `BadGeometry`, `Numeric`, `Interval`,
`MonteCarlo`.
