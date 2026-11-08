# Live trace plot

Status: current

Parent: [plots.md](plots.md), [../server/websocket.md](../server/websocket.md). Code:
`web/src/ws/**` (decoder, client), `web/src/hooks/useTrace.ts`, `web/src/plots/live/**`.

## Data path

1. `ws/frame.ts` `decodeFrame(ArrayBuffer)` mirrors `sadi.server.framing.decode` byte for byte and
   returns a `Result` (`short | magic | version | type`); it never throws. TRACE frames carry per
   channel min/max `Float32Array`s; RESULTS_ENVELOPE frames carry the JSON body and the stale flag.
2. `ws/messages.ts` `parseMessage` types the JSON side channel (`hello`, `state`, `result`,
   `analysis_failed`, `stopped`, `guidance`, `stats`; unknown kinds become `other`).
3. `ws/client.ts` `openStream` opens `WS /api/stream` (binary type arraybuffer), routes data, and on
   loss reconnects with capped exponential backoff (250 ms doubling to 8 s; reset on open),
   publishing a `ConnState` (`connecting | open | reconnecting | closed`). Socket and timers are
   injectable for tests.
4. `hooks/useTrace.ts` feeds a `TraceWindow` and publishes one snapshot per animation frame.

## Window and drawing

`plots/live/window.ts` `TraceWindow` keeps the last `spanS` seconds (default 10) of one channel.
Bucket spacing is `dt_s` for undecimated frames; for frames at the 256-bucket cap it is estimated
from the gap between frame `t0` values (first frame falls back to `dt_s`). Frame seq gaps are
counted as dropped. `snapshot(columns)` merges buckets into at most `columns` display columns so
the draw cost is bounded by pixels, not sample rate.

`plots/live/scene.ts` `buildLiveScene` maps a snapshot to a core `Scene` (no second renderer):
min/max envelope band, mid line, dashed saturation limits at +-4.9 V with shaded zones, event
markers (ring = load change, filled = settled capture, cross = captured early), titled plot with
`Time (s)` and `Voltage (V)` axes and a legend. Connection loss, reconnecting and stale data are
shown inside the plot (subtitle and annotation box).

Marks come from the text channel: a new `point_index` in `state` marks a load change at
`now - time_since_load`; `result` marks a settled or forced capture at `window_end` (stream time).

## Export

`LivePlot` listens for F3 (ignored while typing in a text field, via `keys/keymap` `isTextTarget`)
and exports the current scene as 192 dpi PNG through `plots/core` `exportFigure`.

## Performance

`live.test.tsx` benchmarks decode + window + snapshot per frame for 50 kS/s (50 frames/s, 256
buckets, 2 channels) in node and asserts p95 under 8 ms, mean under 4 ms, well below the 16 ms
frame budget. A real-browser 60 fps run is not automated here.

Dev proxy: `web/vite.config.ts` proxies `/api` with `ws: true` so `WS /api/stream` works under `vite dev`.
