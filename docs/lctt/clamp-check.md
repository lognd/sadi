# LCTT pre-test clamp-slip check

Status: current

Owner: ~DQ1C3W6. Code: `python/sadi/labs/lctt/clamp_check.py`.
Tests: `python/tests/labs/lctt/test_clamp_check.py`. Builds on the [slip detector](slip.md).

Before a test, loose clamps are found by loading lightly, holding, unloading, and repeating.

## Procedure

Per cycle: record a zero, apply `load_fraction` (default 10%) of the test load, hold
`hold_s` (30 s), unload, record the zero again. Repeat `cycles` (3) times. Capture each
cycle as a `ClampCycle` (`t_load`, hold `times`/`strain`, optional `load`, `zero_before`,
`zero_after`).

## Verdict

`check_clamp_slip(cycles, config=None)` returns `Result[ClampCheckReport, ClampCheckError]`.
A cycle passes when `detect_slip` finds no events and `|zero_after - zero_before| <=
return_tol`. The check passes only if all cycles pass; otherwise `advice` is
"Re-tighten clamps ...". Errors: `NoCycles`, `NonFinite` (zero readings), `BadHold`
(detector rejected the hold; reason is logged).

## Wizard

`setup_subcheck()` returns the `SetupSubCheck` descriptor (step `setup`, check `clamp-slip`)
with operator guidance built from the config. `LcttLab.steps()` starts with that Setup step
(`plugin.setup_step`, `Phase.SETUP`, device-point capture), ahead of Calibrate on the step rail.
Its completion criterion is `min_points = config.cycles`: `complete` is refused with `NeedPoints`
until one point per cycle is captured; `skip` is never blocked (ticket ~JTJA6QM).

## Setup capture UI (ticket 01M6XA21KQE5WEXAN39683H4S9)

The Setup step body is `web/src/screens/setup/ClampCheckPanel.tsx`. It explains the check, shows the
loading guidance and "cycle N of M", and takes one form per cycle: zero strain before loading, zero
strain after unloading, and the number of slips seen during the hold. Each cycle is appended as a
POINT with phase `setup` (`ClampInputs`: `zero_before`, `zero_after`, `slip_events`) through
`POST /api/session/points`; earlier cycles are never overwritten.

`GET /api/session/clamp-check` (`routes/clamp.py`) returns `ClampStatus` from `clamp_status()`: the
guidance, required cycle count, return tolerance, per-cycle results and, once all cycles are in, the
verdict (`passed`) with the same advice text as `check_clamp_slip`. The verdict is `null` until the
last cycle is captured. Excluded points are ignored.

Setup points are not load points: `results` leaves them out of `n_points`, `analyze` drops them and
the live curve source skips them. Limitation: the UI records operator-entered zeros and an observed
slip count, not raw hold strain, so the slip detector is not run on live data.

A failed verdict (`passed` false) blocks `POST /session/wizard/complete` for `setup` with 422
`step_quality_gate`; repeat the cycles or skip the step explicitly.
