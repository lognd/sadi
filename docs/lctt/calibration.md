# LCTT calibration

Status: current

Owner: ~NQKWT3Y. Code: `python/sadi/labs/lctt/calibration.py`.
Tests: `python/tests/labs/lctt/test_calibration.py`.

The LVDT calibration fits `height = slope * volts + intercept` through the captured
(V, L) points, equivalent to spreadsheet `LINEST(L, V, TRUE, TRUE)` (formulas in
[domain.md](../domain.md) section 3.3). Pure and deterministic, no I/O.

## API

`fit_calibration(volts, heights, u_volts=None, u_heights=None, *, errors_in_both=False)`
returns `Result[CalibrationFit, CalibrationError]`.

`CalibrationFit` (frozen): `slope` and `intercept` as `Measured` (dof n-2, the
slope/intercept correlation registered so downstream RSS uses the full covariance),
`se_slope`, `se_intercept`, `cov_slope_intercept`, `se_regression`, `r2`, `dof`, `n`,
`t95`, the half-widths `u95_slope` and `u95_intercept`, and `residuals`.

`CalibrationFit.ci_band(volts, prediction=False)` gives the fitted height and the 95%
half-width at each voltage: `t95 * sqrt(var_b + 2 v cov + v^2 var_m)` for the mean line,
plus `se_regression^2` when `prediction=True`.

## Uncertainty inputs

- No uncertainties: ordinary least squares, identical to LINEST.
- `u_heights` (scalar or per point, all > 0): weights 1/u^2.
- `errors_in_both=True` with `u_volts`: effective-variance weights
  1/(u_h^2 + slope^2 u_v^2), iterated to a fixed point. `u_volts` is ignored (and a
  warning logged) when the flag is off.
- Standard errors are scaled by the weighted residuals as LINEST does, so a common
  factor on all uncertainties does not change the result; with equal weights the
  result equals plain LINEST.

## Slope versus intercept (Q6)

The cal lengths are absolute heights, so the intercept is an offset, exposed as
`CalibrationFit.offset`. Only the slope feeds strain. `displacement(slope, dV)` and
`height_at(slope, intercept, V)` are plain formulas decorated with `@uncertain`
(written once); `fit.displacement(dV)` and `fit.height_at(V)` call them with the fitted
`Measured` values.

## Errors

`CalibrationError`: `TooFewPoints` (fewer than 3), `LengthMismatch`, `NonFinite`,
`DegenerateX` (all voltages equal), `RankDeficient` (weighted design numerically rank
below 2), `BadUncertainty`, `MissingVoltUnc`, `NotRepresentable`.

## Validation

Tests compare with a hand-written LINEST on the 12-point local calibration set
and with the reference values printed for that set. Slope, intercept, r^2 and t95 agree to 6
digits; standard errors agree to 1e-5 relative, since the file's 7-digit rounded inputs
limit the oracle (the exact refit of the printed points gives se slope 6.734591E-6
against the file's 6.734580E-6). Hypothesis tests cover slope recovery under noise and
weighted fits.

## Consumers

Tare and loading (slope to strain), the calibration plot, and the live
recompute engine consume `CalibrationFit`.
