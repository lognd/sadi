# LCTT capture modes

Status: current

Owner: ~QPQKQEK. Code: `python/sadi/labs/lctt/capture.py`.
Tests: `python/tests/labs/lctt/test_capture.py`.

`CaptureController` drives one point at a time through the
[streaming settle detector](settle.md) and turns each capture into a `PointV1` event
(see the store events model). The clock is injected (`Clock`), so max-wait behaviour is
deterministic in tests. Build it with `CaptureController.create(stream, config,
resolver, clock)`; call `start_point(t)` at each load change, `push(times, lvdt)` for raw
blocks and `tick()` on a timer.

## Modes (`CaptureConfig.mode`)

- `confirm`: nothing is captured automatically; the human calls `accept()` when the
  indicator says settled.
- `auto`: captures as soon as the detector settles; if `max_wait_s` (clock seconds since
  `start_point`) passes first, the point is captured with `forced_early=true` and a
  warning.
- `fixed_dwell`: requires a `StreamConfig` in fixed_dwell mode (and vice versa,
  else `CaptureError.ModeMismatch`); captures once the dwell has elapsed.

## Forced early

`accept()` before the detector has settled records `forced_early=true`,
`settled=false` and returns a warning in `Captured.warnings` (also logged). After
settling it records a normal settled point.

## Point event and re-editing

The averaging window is mapped to the raw WAL seq range by an injected
`RawRangeResolver(start_t, end_t) -> PointWindow | None`; `None` yields
`CaptureError.NoRawRange`. Derived values on the event are audit only. To change a
window, append `set_window_edit(point_id, window)` (an `EditV1` `set_window`); replay
in `sadi.store.events` recomputes the view from raw.

## Errors

`CaptureError`: `NoOpenPoint`, `ModeMismatch`, `NoRawRange`; stream/settle errors pass
through.
