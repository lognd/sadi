# WebSocket stream

Status: current

Parent: [api.md](api.md), [app.md](app.md). Code: `sadi.server.framing` (codec),
`sadi.server.ws` (`StreamHub`, `make_ws_router`). Source of events: the pipeline `Bus`
([../core/pipeline.md](../core/pipeline.md)); events are published only after the raw block is
durable in the WAL, so nothing here can lose raw data.

`AppSettings.bus` enables the endpoint: `WS /api/stream` (not mounted without a bus).

## Messages

- Binary messages: frames below (display data, droppable).
- Text messages: JSON objects with a `kind`: `hello` (first message: `session` from
  `SessionService.info()`, `latest` messages by kind, `bus_dropped`), `state` (settle status),
  `result` (finalized point), `analysis_failed`, `stopped`, `guidance`, `stats`
  (`sent_frames`, `dropped_frames`, every 1 s).
- `hello` also carries `simulated` (bool: the data source is the simulator). `state` carries
  `drift_vps` (server drift rate of the open point in V/s, or null), `window`
  (`first_raw_seq`, `last_raw_seq`: raw-seq span of the open point's capture window; the first
  seq is the first state seen for that `point_index`) and `simulated`. These are JSON-only
  additions: the binary frame layout and version (1) are unchanged, and clients that ignore
  unknown keys keep working. `StreamHub(simulated=callable)` supplies the flag; `create_app`
  derives it from `AppSettings.device.status == "simulated"`.

## Binary frame layout (little-endian)

Header, 24 bytes:

| Offset | Type | Field |
|---|---|---|
| 0 | 4 bytes | magic `SADI` |
| 4 | u8 | version (1) |
| 5 | u8 | type: 1 TRACE, 2 RESULTS_ENVELOPE |
| 6 | u16 | flags: bit 0 = stale |
| 8 | u64 | frame seq (hub-assigned, increasing; gaps mean dropped frames) |
| 16 | f64 | t0_s, stream time of the first sample |

TRACE payload (type 1), follows the header:

| Offset | Type | Field |
|---|---|---|
| 24 | u64 | raw_seq (WAL seq of the source block) |
| 32 | u64 | durable_seq |
| 40 | u64 | enqueued_seq |
| 48 | f64 | dt_s, sample spacing of the undecimated block |
| 56 | u16 | n_channels |
| 58 | u32 | n_points, per channel |
| 62 | per channel | u16 channel id, then n_points x (f32 min, f32 max) interleaved |

Each channel is min/max-decimated to at most 256 buckets (peaks survive); a channel with
fewer points has min == max. Total size: `62 + n_channels * (2 + 8 * n_points)` bytes.

RESULTS_ENVELOPE (type 2) carries the versioned results envelope defined by J4
(version, stale flag, progress): payload after the header is UTF-8 JSON, flags bit 0 is the
stale flag. `StreamHub` emits it for each `ResultsStream` envelope (snapshot on connect, then
live); see [results-stream.md](results-stream.md).

The TypeScript decoder in F4 mirrors `framing.decode` byte for byte.

## Back-pressure and resume

Each client has a queue of 8 display frames; when full the oldest is dropped and
`dropped_frames` is incremented (reported in `stats`; gaps in frame seq show it too).
JSON messages are queued up to 1024 and are not dropped under normal load. The bus
subscription itself is drop-oldest and counted. WAL writes are never throttled by clients.
A reconnecting client gets `hello` with the latest state and then live frames; missed
frames are not replayed (the WAL is the record).

## Budget at 50 kS/s

The pipeline decimates each block to at most 256 points; at 50 kS/s with 1000-sample blocks
that is 50 frames/s of about 2 KB (2 channels), roughly 100 KB/s. The test
`test_50ksps_real_time_budget` runs 2 s of real-time publishing and requires at least 95% of
frames delivered with p95 publish-to-receive latency under 100 ms (in-process).

Versioned results (analytic, refining, stale markers) are specified in
[results-stream.md](results-stream.md).
