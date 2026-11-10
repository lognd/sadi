# LCTT GP load selector

Status: current

Owner: ~5MQ11EV. Code: `python/sadi/labs/lctt/gp_suggester.py`.
Tests: `python/tests/labs/lctt/test_gp_suggester.py`.

`GpLoadSuggester` is the default `LoadSuggester` used by `guide()` and `GuidedRun` (see
[guidance](../lctt/guidance.md)). It is advisory: it proposes the next total load, the user
decides. It never proposes a load outside the `LoadRange`, is deterministic (no randomness; ties
go to the lowest candidate index), and falls back to `EvenScheduleSuggester` on any failure
(non-finite data, singular matrices), reporting `gp_state = "unreliable"`.

The suggester holds the accepted points as `Observation(load_kg, response)` (response is e.g.
strain). Feed it with `observe(load_kg, response)`; `reset()` clears it. The candidate set is
41 evenly spaced loads over the range (`N_CANDIDATES`), and loads are normalised to x in [0, 1].

## Cold start (fewer than 3 points)

Point 0 is the minimum load, point 1 the maximum, then bisection midpoints in van der Corput
order (1/2, 1/4, 3/4, 1/8, ...). Without observations the point index is `results.n_points`.

## Elastic phase: c-optimal slope

Model y = a + b x with a weak ridge prior (precision 1e-6). With noise variance s2 (residual
estimate when n > 2, else the `noise_var` default 1e-4) the posterior covariance is
C = (Phi^T Phi / s2 + 1e-6 I)^-1. Adding a point with features phi = (1, x_c) gives, by
Sherman-Morrison, the new slope variance

    var_b' = C11 - (C phi)_1^2 / (s2 + phi^T C phi)

The chosen candidate minimises var_b' (maximises the expected reduction of the modulus-slope
95 % half-width, 1.96 sqrt(var_b) per kg). The gain is `hw_now - hw_after`.

## Plastic phase: GP information gain

A zero-mean GP over (load, response) with a Matern 5/2 (default) or RBF kernel, length scale 0.25
of the range, signal variance var(y), noise s2. The posterior variance at each candidate is
v_c; the score is the information gain 0.5 ln(1 + v_c / s2). The expected half-width is
1.96 sqrt(mean posterior variance over candidates) after the rank-one update at the choice.

## GuidanceState fields (all optional, backward compatible)

- `expected_gain`: reduction in half-width expected from the suggested point (None if no model).
- `expected_half_width`: the half-width expected after taking it.
- `alternatives`: the top 3 candidate loads, best first (empty during cold start).
- `gp_state`: advisory only. `collecting` (default), `enough` (guidance would stop early),
  `diminishing` (gain below 2 % of the current half-width after 5 points), `unreliable`
  (noise exceeds signal, or the fallback was used). Empty when no suggestion applies.

`LoadSuggestion` carries the same four optional fields.

## Capture input ranges and the calibration gate

Capture rejects values that look like unit slips and keeps the typed text so nothing is lost.
Server limits (`python/sadi/core/point_inputs.py`) and the UI `plausible` ranges
(`web/src/screens/run/inputFields.ts`) agree:

| Field | Range | Hint |
| --- | --- | --- |
| Gauge height | -1 mm .. 0.1 m | `1` looks like millimetres; did you mean `0.001`? |
| Masses (`mass_kg`, `hanger_kg`) | 0 .. 20 kg | `500` looks like grams; did you mean `0.5`? |
| Specimen diameter | 0.05 mm .. 5 mm | now required on the Tare step |

"Finish LVDT calibration" is blocked unless the fit has r2 >= 0.999, a positive slope and no point
whose residual exceeds 3 standard errors; the message names the worst point (leave-one-out).
If no specimen diameter reached the analysis, results use 6 mm +/- 20 % and carry the note
"diameter assumed 6 mm ...".
