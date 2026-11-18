# LCTT settle detector

Status: current

Owner: ~7Q9BX19 (pure detector). Code: `python/sadi/labs/lctt/settle.py`.
Tests: `python/tests/labs/lctt/test_settle.py`.

The detector only SUGGESTS that the LVDT has settled after a load change; a human
confirms (see [data safety](../data-safety.md)). Raw samples are always recorded; the
detector is pure, deterministic and does no I/O.

## Algorithm

`detect_settle(times, lvdt, config)` returns `Result[SettleResult, SettleError]`.
For each sample the trailing `window_s` window is fitted by least squares, giving the
drift rate (V/s) and its standard error. A sample "meets the criterion" when
`|slope| + unc_factor * se <= threshold` and the window holds at least `min_points`
samples spanning a full `window_s`. The signal is settled once the criterion holds
continuously for `min_dwell_s`. `settled_index` is where the run began,
`confirmed_index` where the dwell completed.

## Output

`SettleResult`: `settled`, `settled_index`, `settled_time`, `confirmed_index`,
`slope` (a `Measured` in V/s, dof n-2) and, when not settled, `reason`:
`insufficient_data`, `slope_above_threshold`, `slope_uncertain`, `dwell_not_reached`.

## Config

`SettleConfig` is frozen with validated bounds: `window_s`, `threshold`, `min_dwell_s`,
`min_points` (>= 3), `unc_factor`.

## Errors

`SettleError`: `LengthMismatch`, `NonFinite`, `NonMonotonicTime`, `SlopeUnavailable`.

## Streaming layer

Owner: ~H1A73VD. Code: `python/sadi/labs/lctt/settle_stream.py`.
Tests: `python/tests/labs/lctt/test_settle_stream.py`.

`StreamingSettleDetector` wraps `detect_settle` for live acquisition. Feed raw LVDT
blocks with `push(times, lvdt)` and load-change marker events with
`mark_load_change(t)`. Every sample is appended to `raw` whatever the state; samples
before the first marker belong to no point.

`StreamStatus.state` for the open point: `loading` (no full window since the load
change yet), `creeping` (window fitted, criterion not met) or `settled` (latched; later
blocks do not un-settle it). It carries `time_since_load` and `drift_rate` (a `Measured`
in V/s). A new marker finalizes the open point as unsettled.

Each finalized point is a `PointRecord`: `window_start`/`window_end` (final fitted
window), `time_since_load` (at settle onset, or at the last sample if unsettled),
`drift_rate`, `settled`, `forced_early`, `mode`, `n_samples`. `force_early()` closes an
unsettled point with `forced_early=True`; `close_point()` closes it as it stands.

`StreamConfig.mode` is `drift` (default) or `fixed_dwell`; the latter needs
`fixed_dwell_s` and settles when that time has passed since the load change, regardless
of drift (the drift rate is still reported). Errors: the `SettleError` set for bad
blocks plus `StreamError` (`BadMarker`, `NoOpenPoint`). Each push re-runs the detector
over the open point's samples (O(n) per block), which is fine for lab-scale points.

## Live defaults (server)

`sadi.server.live.LIVE_SETTLE` is `window_s=0.5`, `threshold=0.05` V/s, `min_dwell_s=0.5`,
`min_points=10`. A 20 ms window has a slope standard error near 0.13 V/s, so the old defaults
declared "settled" while the signal still drifted at 113 mV/s (audit1 #18).
