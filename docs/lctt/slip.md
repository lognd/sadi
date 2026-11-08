# LCTT slip detector

Status: current

Owner: ~T3M5GJG. Code: `python/sadi/labs/lctt/slip.py`.
Tests: `python/tests/labs/lctt/test_slip.py`. Fixture: `python/tests/fixtures/short_slip/`.

Clamp slip shows up as a sudden strain step with no load change; creep is smooth and
decays in log time (see [creep fit](creep.md)). `detect_slip(times, strain, t_load, load=None,
config=None)` returns `Result[SlipReport, SlipError]` for one hold (pure, no I/O).

## Method

Each first difference of strain is compared with the median of its `window` neighbours on
each side (a Hampel filter). Smooth creep has near-equal neighbouring differences and
cancels; a step does not. The white-noise sigma is the MAD of those residuals, so a few
steps do not inflate it. A jump is a slip when `|residual| > k * sigma_d` (default k = 5,
sigma_d the residual-difference sigma), `|size| >= min_size`, and the load did not change
across it (`load_tol`, only when `load` is given). Anything else is classed as creep.
`SlipReport.creep_slope` is the pooled log-time slope with a separate intercept per
segment between events, so it is the creep rate with slip removed.

`SlipEvent`: `time` and `index` of the first sample after the step, `size` (strain,
signed), `z` (size over sigma_d) and `confidence = erf(z / sqrt 2)`.

Limits: the first `window` jumps of a hold are not evaluated (onset creep is steepest and
cannot be cancelled from one side); slips there are missed and logged at debug level.
Two slips closer than `window` samples can mask each other.

## Performance bound

On seeded synthetic holds (creep 2e-4 * ln(1 + dt/20), white noise sigma 2e-6, 120
samples, 5 s spacing, 300 slip trials with signed steps of 15 to 150 sigma at random
positions, plus 300 slip-free holds): 100% of injected steps are found and the
false-positive rate stays at or below 1% (`FP_BOUND` in the test; measured 0).

## Fixture: short-run stand-in

A slip-contaminated short run (clamp slip suspected) is not in the repo; it must never
calibrate E or other physics. `short_slip/short_slip.csv` is a seeded synthetic stand-in
with the same failure shape (load constant at 50 N, two steps). `expected.json` lists the
rows that must be flagged: index 40 (t = 305 s, 4.0e-5) and index 85 (t = 530 s, 2.5e-5),
and nothing else. Used only as a detection test case.

## Real data: local short run

Ticket ~E5AM8Q6. A 41-row local time series (a concatenated multi-load ramp) was run
through `detect_slip` with `t_load = 0` (trimmed local copy, gitignored; test
`tests/labs/lctt/test_real_data.py`, skipped when the data is absent).

- Without `load`: 3 events, each coinciding with a load increase, so they are load
  steps, not slip.
- With `load` (`load_tol = 0`): all three are classed as load changes; 0 events.
- Noise sigma is far above the detector's design regime because the series is one
  concatenated ramp, not a single constant-load hold; each constant-load segment has
  fewer than `2*window + 1` samples.

Conclusion: the detector finds no clamp slip separable from load steps in this series.
The series is too sparse per hold to confirm or exclude slip, so it stays a detector
test case only.

## Consumers

The pre-test clamp-slip check and the creep plot (slip markers) consume `SlipEvent`s. The
detector only reports; a human decides what to do with a flagged hold.
