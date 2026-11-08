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
with operator guidance built from the config. Registering a Setup step in the LCTT lab
needs a core `Phase` value and is tracked separately.
