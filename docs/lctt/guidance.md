# LCTT guided run

Status: current

Owner: ~G2YNMJB. Code: `python/sadi/labs/lctt/guidance.py`.
Tests: `python/tests/labs/lctt/test_guidance.py`.

Phase-wise guidance for a run: calibrate (LVDT), elastic (long wire, E) and plastic (short
wire, yield). It consumes the live `ResultSet` (see [live results](live-results.md)) and
returns a `GuidanceState`. It is pure: calling it never changes the phase.

## API

- `guide(phase, GuidanceInput, config=None, suggester=None)` -> `Result[GuidanceState,
  GuidanceError]`. `GuidanceInput` holds the `ResultSet`, the calibration point count and a
  `HoldState` (`ready`, `creeping`, `awaiting_accept`).
- `GuidedRun` keeps the current phase. It only advances through `accept_transition()`.

## GuidanceState

- `next_action`: `Wait: creeping` while creeping, `Press Space to accept` once settled,
  otherwise the suggester text (e.g. `Use weights 3, 5, 6`) or `Record calibration point N`.
- `expected_value` and `unit`: the phase's key result (`slope`, `E`, `yield_stress`).
- `confidence`: current 95 % half-width against the user's relative target (`target`,
  default 5 %); `fraction` is progress to the target (1.0 when met).
- `stop_early` and `stop_reason`: set when the target is met after the minimum points
  (3 calibration points, 5 load points).
- `proposed_next_phase` (and `run_complete_proposed` in the last phase): a proposal only.
  The user may ignore it and keep adding points; nothing is forced.

## Load suggestion and safety

Load choice is pluggable through the `LoadSuggester` protocol (`suggest(phase, results,
load_range) -> Result[LoadSuggestion, GuidanceError]`). The built-in
`EvenScheduleSuggester` steps evenly over the safe range. Richer selectors (weight
combinations and sequencing) can be supplied by a plugin; tracked code does not depend on any.
Every suggestion is checked against `LoadRange`; a non-finite or out-of-range load is refused
with `GuidanceError.UnsafeLoad` and never shown.

## Bound on run length

Each phase has a point cap: calibrate 8, elastic 12, plastic 15. At the cap guidance stops
suggesting loads and proposes the phase end, so a complete three-phase run is at most
`MAX_RUN_POINTS` = 35 points even if the target is never met. The simulator test follows the
guidance through all three phases with an unreachable target and ends at exactly this bound.
