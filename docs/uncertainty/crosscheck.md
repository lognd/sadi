# Uncertainty cross-check suite

Status: current

Tests: python/tests/uncertainty/crosscheck/test_labs_crosscheck.py. Complements
[fallbacks.md](fallbacks.md): it reuses `Uncertain.cross_check` (analytic, numeric finite
difference and Monte Carlo) rather than adding a second engine.

## Coverage

Every `@uncertain` lab formula is parametrised, each with independent and correlated inputs:
`height_at`, `displacement` (calibration), `load_force`, `cross_area`, `stress`, `strain`
(loading), `secant_modulus`, `chord_modulus` (E), `yield_stress`, `yield_strain` (yield).
Correlated runs chain neighbouring inputs with rho = 0.4 through the covariance registry, so
analytic `J C J^T`, numeric `J C J^T` and the Monte Carlo sampler all use the same matrix.

## Documented tolerances

| Quantity | Tolerance |
|----------|-----------|
| value and std_unc, any pair of methods | 3 % of the larger plus 4 sigma of MC sampling error |
| symbolic partial vs independent Ridders difference | rel 1e-6 |

Settings: relative input uncertainty 0.5 %, 40000 MC samples (seeded, deterministic). Nominal
values have magnitude >= 1 and well-conditioned denominators, since first-order propagation is
only expected to match MC when the formula is near linear over the input spread.

## Degenerate inputs

Hypothesis drives exact-zero and tiny (1e-12 to 1e-3) divisors through all methods; each must
return `Ok` or a typed `Err`, never raise. Two strict xfails pin known engine defects: ~SJ9VQC9
(numeric step floor fails for SI-small inputs such as area 1.2e-4 m^2) and ~0FYTGN8 (overflow
for divisors below ~1e-80 raises instead of returning an error). Remove each xfail with its fix.
