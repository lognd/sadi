# LCTT live results

Status: current

Owner: ~19WDD6Q. Code: `python/sadi/labs/lctt/live.py`, `python/sadi/core/results.py`.
Tests: `python/tests/labs/lctt/test_live.py`.

After every captured point the engine recomputes every result from the RAW event stream
(block-mean volts, hanging mass, calibration samples, tare blocks, specimen geometry). It
never reads a cached display value.

## API

- `recompute(events, config=None, cache=None)` -> `Result[ResultSet, LiveError]`. Pure and
  synchronous; analytic RSS only. Errors: `UnknownPoint` (edit names an unseen id),
  `DuplicatePoint`, `BadInput`.
- Events (`LiveEvent`, discriminated by `kind`): `CalPoint`, `TareBlock`, `SpecimenSetup`,
  `LoadPoint`, and the review edits `OverridePoint`, `ExcludePoint`, `SetWindow` (inclusive
  indices among the active points; default is all active points).
- `LiveEngine.add(event)` appends one event and returns the updated `ResultSet`. It keeps a
  per-point `LoadCache`, so only the new point runs the uncertainty engine. The result is
  exactly equal to `recompute(all events)` (property test).

## ResultSet

`ResultSet.values` holds `ResultValue` entries named `slope`, `intercept`, `calibration_r2`,
`tare`, `E`, `r2`, `yield_stress`. Each has value, standard uncertainty, `u95` (t95 of the
dof times u), `low95`/`high95`, a class-rule display string (3 s.f. value, 2 s.f. U), and a
plain-language confidence string. Results that cannot be computed yet are listed in
`pending`; warnings (low r^2, saturation, no yield crossing) are in `notes`.

## Heavy work is a job

Monte Carlo is never run inline. `ResultSet.refinement` names the results (`E`,
`yield_stress`) for which a J3 job should run MC. Each `ResultValue.mc` starts `pending`;
when the job returns, `with_mc(result, {name: mc_std_unc})` fills the RSS vs MC cross-check
flag (`agrees` / `disagrees`, tolerance `MC_AGREE_TOL`, 10 %).

## Latency

A fresh covariance registry gives a median update under 50 ms at 200 points. The global
registry grows per `Measured` and slows the tail; tracked in a separate bug ticket.
