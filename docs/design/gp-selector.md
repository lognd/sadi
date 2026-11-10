# Sequential-design selector (next weight)

Status: current

Owner: ~PV143B4. Code: `python/sadi/design/` (`selector.py`, `models.py`, `benchmark.py`),
route `python/sadi/server/routes/design.py`, UI `web/src/screens/run/SuggestedWeightPanel.tsx`.
Tests: `python/tests/design/test_selector.py`, `python/tests/server/test_design_route.py`.
Spec: `private/final-project/docs/gp-selector.md`. The older per-call suggester is described in
[labs/lctt-gp-selector.md](../labs/lctt-gp-selector.md).

## What it does

`select_next(phase, obs, candidates, target, config)` returns `Result[DesignAdvice, SelectorError]`:
a `NextSuggestion` (candidate, expected gain, up to 3 alternatives, a plain `why` sentence) and a
`ConfidenceIndicator` (state, ratio of current to target half-width, `consecutive_ok` of `patience`).
It is advisory only: the route is GET, nothing is written, the user picks the weight.

- LVDT calibration and elastic phases: Bayesian line fit, target is the slope (E is proportional to
  it). The gain of a candidate is the expected shrink of the 95 % slope half-width (rank-one update).
  A new point far off the line (> 4 predictive sd) gives `unreliable` / `departure_from_linear`.
- Yield phase: Matern52 GP on the departure from the elastic line, hyper-parameters chosen by log
  marginal likelihood on a fixed grid; target is the 0.2 % offset crossing (offset given in response
  units, a documented approximation). Not reached gives `yield_not_reached` and an upward exploration.
- Stop rule: enough means half-width <= 0.9 x target for `patience` (2) consecutive prefixes and at
  least `n_min` points (3 linear, 5 yield). Below `n_min` the state is `unreliable` with reason
  `cold_start`, a space-filling load is suggested and stop is never recommended.
- Deterministic: no RNG in the selector; `seed64` (blake2b) seeds the benchmark. Time only sets
  `budget_exceeded` (150 ms). Typical latency is a few ms.

## Why the Run screen showed nothing before

The old GP panel components were never mounted, the WebSocket guidance note carried no GP fields, and
`guide()` built a fresh suggester with zero observations on every call, so it always returned the cold
start schedule. The Run screen now mounts `SuggestedWeightPanel`, which reads `/api/design/next-weight`
after every captured point.

## Route

`GET /api/design/next-weight?phase=elastic|lvdt_cal|yield&target=0.05[&offset=...]`. Only active,
settled (or force-accepted) points of the matching phase are used. Load range 0..5 kg, 41 candidates.
The yield phase uses plastic points only (elastic and plastic are different specimens); the
indicator `n` counts plastic points. Elastic and yield suggestions are loads at or above the
current hang and never 0 kg once a point exists; cold start steps up evenly from the smallest real
mass, and the elastic run is capped at 60 % of the range, below the expected yield load.

## Benchmark

`sadi.design.benchmark.run_benchmark` compares the selector with random and binary-search policies on
seeded synthetic data (final half-width, error, coverage). Run with BLAS limited to one thread.

## Weight plan

The ordered choice of which inventory weights to hang is described in [weight-plan.md](weight-plan.md); it reuses
`select_next` as its gain machinery.
