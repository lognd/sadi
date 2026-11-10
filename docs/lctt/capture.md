# LCTT capture modes

Status: current

Owner: ~QPQKQEK. Code: `python/sadi/labs/lctt/capture.py`.
Tests: `python/tests/labs/lctt/test_capture.py`.

`CaptureController` drives one point at a time through the
[streaming settle detector](settle.md) and turns each capture into a `PointV1` event
(see the store events model). The clock is injected (`Clock`), so max-wait behaviour is
deterministic in tests. Build it with `CaptureController.create(stream, config,
resolver, clock)`; call `start_point(t, mass_kg, u_mass_kg=0.0)` at each load change (total hanging mass), `push(times, lvdt)` for raw
blocks and `tick()` on a timer.

## Modes (`CaptureConfig.mode`)

- `confirm`: nothing is captured automatically; the human calls `accept()` when the
  indicator says settled.
- `auto`: captures as soon as the detector settles; if `max_wait_s` (clock seconds since
  `start_point`) passes first, the point is captured with `forced_early=true` and a
  warning. After a capture the detector auto-opens the next point and the max-wait clock
  restarts for it.
- `fixed_dwell`: requires a `StreamConfig` in fixed_dwell mode (and vice versa,
  else `CaptureError.ModeMismatch`); captures once the dwell has elapsed.

## Forced early

`accept()` before the detector has settled records `forced_early=true`,
`settled=false` and returns a warning in `Captured.warnings` (also logged). After
settling it records a normal settled point.

## Auto-capture and re-arming

`CaptureController` in auto mode captures once per `start_point` (armed flag). After a
capture it will not record the same load again until the next `start_point`, so a
signal that stays settled cannot produce duplicate points. A human `accept()` is
unaffected.

## Point event and re-editing

The averaging window is mapped to the raw WAL seq range by an injected
`RawRangeResolver(start_t, end_t) -> PointWindow | None`; `None` yields
`CaptureError.NoRawRange`. Derived values on the event are audit only. To change a
window, append `set_window_edit(point_id, window)` (an `EditV1` `set_window`); replay
in `sadi.store.events` recomputes the view from raw.

## Recording

Each `Captured` carries `meta` (a `PointMeta`: `t_since_load_s`, `drift_rate`, `settled`, `forced_early`) and `inputs`, a `LoadInputs` (see `sadi.core.point_inputs`): `volts`
is the mean raw LVDT volts over the averaging window, `u_volts` its standard error,
`mass_kg`/`u_mass_kg` come from `start_point`, and `phase` is `CaptureConfig.phase`.
`point` is built with `build_point`, so its `inputs` use the shared phase mapping. Write it
with `AcquisitionDriver.record_point(captured.inputs, captured.point.window, captured.meta)` (labs may not
import `sadi.api`; the caller does). `recover_state` and the server curve source then
replay the point as a load point. The POINT event persists phase, window, inputs and the
`meta` fields, so settled/forced-early/drift survive crash recovery; events written without
them read back as defaults.

## Errors

`CaptureError`: `NoOpenPoint`, `ModeMismatch`, `NoRawRange`; stream/settle errors pass
through.
