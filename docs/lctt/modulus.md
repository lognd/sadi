# LCTT modulus, yield and saturation

Status: current

Owner: ~TQ7ZKZW. Code: `python/sadi/labs/lctt/modulus.py`, `yield_.py`, `saturation.py`.
Tests: `python/tests/labs/lctt/test_modulus.py`.

Pure, no I/O; builds on [loading](loading.md) stress and strain `Measured` values.
Synthetic tests only: `short-data.csv` is slip-affected and is not used to validate E.

## E fit

- `CurvePoint(index, stress, strain, settle_source, saturated)` is one captured point.
- `fit_modulus(points, first, last, config)` -> `Result[ModulusFit, ModulusError]`.
  The window is manual (inclusive indices, at least 3 points, Q3). It reuses
  `fit_calibration` (OLS, LINEST-equivalent) with strain as x and stress as y.
- `ModulusFit`: `modulus` (Measured, Pa, std unc = regression SE, dof n-2), `std_error`,
  `u95` (t95 * SE), `r2`, `n`, window, `low_r2` (r^2 below `ModulusConfig.r2_threshold`,
  default 0.995), `saturated_points`, `settle_sources` and `budget`.
- `settle_sources` records, per fitted point, `SettleSource`: `settled_window`,
  `forced_early` or `fixed_dwell`.
- `suggest_window(points, config)` is a hint only: the longest window meeting the r^2
  threshold. It never changes the manual window.
- `secant_moduli(points)` gives per-point `secant_modulus = stress / strain` (`None` where
  strain is zero).

## U4 budget for E

`chord_modulus(s_first, s_last, e_first, e_last)` is a plain `@uncertain` function; the
`ModulusFit.budget` is its ranked per-input `Budget` for the window end points. It shows
which measured input (stress or strain at the ends) dominates the measurement uncertainty,
alongside the regression SE of the fit. The two are reported separately, not summed.

## Yield and ultimate

`find_yield(points, modulus, offset=0.002)` intersects the polyline with
`sigma = E (eps - offset)` using the `@uncertain` forms `yield_stress` and `yield_strain`
(linear interpolation inside the bracketing segment, E and inputs fully correlated by the
engine). It also returns the ultimate stress (maximum stress point). Errors: `NoCrossing`,
`TooFewPoints`.

## Saturation

`check_saturation(point_index, volts, config)` raises a typed `SaturationFlag` when any
|V| exceeds `SaturationConfig.threshold_v` (default 4.9 V). The three figures differ by
source: 4.8 V is the mounting guidance, 4.9 V is the warning default, and 5.12 V is the
ADC full range (Q14, see [open-questions](../open-questions.md)). All are configurable.

## Reported E interval (audit1 #7)

`LcttLab.analyze` adds, in quadrature to the regression standard error, a calibration-slope
term, a diameter term (stress scales with 1/d^2) and a 3 % creep allowance
(`CREEP_REL_ALLOWANCE`), because creep biases a fitted E low and the bare OLS SE missed the
truth in most synthetic seeds. `analyze` also returns `slope` (m/V), `intercept` (m) and
`tare` (V), and carries `pending`/`notes` from `combine_runs` into `AnalysisResult`.
