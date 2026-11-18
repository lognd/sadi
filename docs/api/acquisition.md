# Acquisition driver

Status: current

Owner: ~62E6T8C. Code: `python/sadi/api/acquisition.py`.

`sadi.api.acquisition.AcquisitionDriver` connects a block source (the `DeviceService`, or any
object with `next_block` / `stop_streaming`) to `AcquisitionPipeline`.

- Acquire loop thread: `next_block` -> `pipeline.ingest`, so every block is written to the WAL.
  A device error halts the pipeline loudly via the public `pipeline.halt()` (marker plus `PipelineStopped`) and is kept on
  `driver.fault`; a pipeline refusal stops the loop and is also kept as a fault.
- Tick timer thread: `pipeline.tick()` every `tick_interval_s` (default 0.5 s); a failed or
  stalled writer records a `wal` fault and stops the loop.
- `stop()` joins both threads, ingests the blocks the device returns from `stop_streaming`
  (queued plus trailing), then drains the pipeline. Nothing is dropped silently.
- Load chain: `LoadChain` is an ordered tuple of `LoadStep(label, mass_kg)`. `next_load()`
  writes a `load_applied` marker through the pipeline and only then advances the cursor, so a
  refused marker never skips a step. Errors are typani `Err` values (`AcquisitionError`).
- Recording points: `record_point(inputs, window, meta=None)` writes a WAL POINT event (via `AcquisitionPipeline.record_point`) using the typed inputs of `sadi.core.point_inputs` (calibration, tare, specimen, load); the same module is what the server curve source reads, so recorded points feed `/api/stress-strain/fit`. The optional `PointMeta` (`t_since_load_s`, `drift_rate`, `settled`, `forced_early`) is persisted on the POINT too, so recovery loses no settle provenance; older events without it read as defaults (`parse_meta`). Append-only; a WAL refusal halts the pipeline like any other write.

`POST /api/session/points` takes an optional `request_id` (1-128 chars, persisted on the POINT). A retry with the same id, including one after a durability timeout, returns the original commit (same `seq`) and never records a second point.
