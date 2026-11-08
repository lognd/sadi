# LCTT loading: tare, load, stress, strain

Status: current

Owner: ~9TZ8D2S. Code: `python/sadi/labs/lctt/loading.py`.
Tests: `python/tests/labs/lctt/test_loading.py`.

Pure, no I/O. Closed forms are in [domain.md](../domain.md) sections 3.2 and 3.4; every
quantity goes through the `@uncertain` engine (see [uncertain](../uncertainty/uncertain.md)),
so correlated inputs use the full covariance. The domain's `U` values (2 s, 2 Sx) are
stored as the `Measured.std_unc` and combined by RSS exactly as the closed forms do.

## API

- `block_voltage(mean, sd, n, rule)` -> `Result[Measured, LoadingError]`. Option
  `VoltageUncertainty.TWO_S` (default, Q5): U_V = 2 s. Alternative `TWO_S_OVER_SQRT_N`: 2 s / sqrt(n).
- `pool_tare(means, sds, counts)` pools B blocks (domain 3.2): M, Sx, U_tare = 2 Sx.
- `load_force(mass_total, hanger_mass, g)`, `cross_area(diameter)`, `stress(force, area)`
  and `strain(slope, volts, tare, l0)` are plain `@uncertain` functions written once.
  `latex_forms()` returns their `.latex` for the results panel and report.
- `compute_loading(inputs, options)` -> `Result[LoadingResult, LoadingError]` with load,
  area, stress, strain and warnings. Load = (sum of inventory masses + hanger) * g, g = 9.80665 exact.
  The inventory itself is not in the tracked tree; callers pass each mass as a `Measured`.

## Options (`LoadingOptions`, frozen)

| Option | Default | Notes |
| --- | --- | --- |
| `voltage_uncertainty` | `two_s` | Q5; alt `two_s_over_sqrt_n` |
| `sign_policy` | `warn` | Q10; a negative slope warns, `flip` negates it (the UI one-click flip sets this) |
| `specimen` | `short` | Q8; L0 default 0.08313 m (short) or 0.5 m (long) |
| `l0` | none | Always-editable override in metres; `LoadingInputs.l0` (a `Measured`) wins over both |

## Validation

Tests compare against the domain closed forms computed independently in the test. A
private, locally run test also checks every row of a recorded short-run file at 1e-9
(force, stress, strain and their uncertainties); it skips when that file is absent.
