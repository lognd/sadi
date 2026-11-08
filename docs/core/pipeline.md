# Acquisition pipeline

Status: current

Owner: ~60ZNFTD. Code: `python/sadi/core/pipeline.py`.
Tests: `python/tests/core/test_pipeline.py`.

Raw blocks flow raw -> WAL (durable) -> analysis -> display. The rule (invariant I6 in
[data safety](../data-safety.md)): display and analysis see a block only after
`durable_seq` covers it. There is no "show unsaved data" mode.

## Flow

1. `AcquisitionPipeline.ingest(block)` encodes a `RAW_BLOCK`, submits it to the WAL writer
   thread and parks the block with its seq. It returns immediately; acquisition never waits
   on fsync.
2. The forwarder (`start()` thread, or `pump()` driven by the caller) calls `wait_durable`
   and releases parked items whose seq is `<= durable_seq`, in order.
3. Release runs the settle detector and publishes `TraceFrame` (decimated to
   `max_frame_points`), `SettleUpdate` and `ResultUpdate` onto the `Bus`.

Load changes, point closes and early-force requests (`mark_load_change`, `close_point`,
`force_early`) are written as `MARKER` records and parked in the same queue, so markers and
blocks stay ordered.

## Failure behaviour

- WAL error, backpressure or stall (`tick()` runs `check_health`): the pipeline halts once. It
  stops the device, writes a best-effort `MARKER(kind="acquisition_stopped")`, publishes
  `PipelineStopped` (reason plus UI hint) and refuses further `ingest` with
  `PipelineError.Halted`. Parked undurable items are never displayed.
- A malformed block returns `PipelineError.BadBlock`; nothing is enqueued and acquisition
  continues.
- An analysis exception is logged and published as `AnalysisFailed`. It never touches raw
  data or halts acquisition.
- Bus subscriptions are bounded and drop the oldest event when full (`Subscription.dropped`
  counts them), so a slow display loses only derived events.

- A block with `dropped_bytes > 0` carries junk at unknown positions, so every received byte
  is stored verbatim as one `RAW_JUNK` record (reason 1, resync) instead of a `RAW_BLOCK`;
  nothing is lost and the packets can be re-decoded from it. Analysis still runs from the
  decoded volts once that record is durable.

## Not yet wired

Device/API wiring and the writing indicator are follow-up tickets.
