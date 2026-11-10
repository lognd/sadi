# Live trace plot

Status: current

Parent: [plots.md](plots.md), [../server/websocket.md](../server/websocket.md). Code:
`web/src/ws/**` (decoder, client), `web/src/hooks/useTrace.ts`, `web/src/hooks/markClock.ts`, `web/src/plots/live/**`.

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

### Clock audit (verified)

One clock everywhere: sample time `t0_s + i / sample_rate_hz` (set in `core/pipeline.py`, packed as
the frame header `t0_s`, fed to the settle detector as its `times`). Hence `PointRecord.window_end`
and `load_change_time` are absolute stream times, equal to the clock of trace frames, so
`window_end` is used verbatim. `time_since_load` is a duration (last sample - load time, or
settled time - load time once latched), so a load mark is `now - time_since_load` where `now` is the
window end (`t0 + n * bucket`). The only skew is under one bucket (the window end is one sample
past the last sample). The state message arrives after its trace frame, so `now` is current. No
Python change is needed. Pure helpers: `web/src/hooks/markClock.ts` (`loadMarkTime`,
`resultMarkTime`), pinned by `markClock.test.ts`.

## Export

`LivePlot` listens for keydown and acts when `keys/keymap` `resolveKey` returns the `export` action
(F3; inert while typing in a text field, so the key binding lives only in the keymap)
and exports the current scene as 192 dpi PNG through `plots/core` `exportFigure`.

## Performance

`live.test.tsx` benchmarks decode + window + snapshot per frame for 50 kS/s (50 frames/s, 256
buckets, 2 channels) in node and asserts p95 under 8 ms, mean under 4 ms, well below the 16 ms
frame budget.

### Real-browser 60 fps benchmark (opt-in)

The 60 fps result in a real browser is UNVERIFIED: no browser was available when this was built, and
nothing runs it by default (it is not part of `vitest run`). The harness exists so a human can run it:

- `plots/live/framestats.ts` holds pure helpers (`intervals`, `percentile`, `summarize`,
  `meets60fps`); they are unit tested in `framestats.test.ts`. `meets60fps` requires mean >= 58 fps
  and p95 interval <= 1.25 x 16.67 ms.
- `plots/live/bench.ts` `runFrameBench(env)` runs 600 animation frames of decode + window +
  snapshot with an injectable clock and scheduler (the unit test uses a fake 60 Hz clock);
  `installBench()` exposes `window.__sadiLiveBench()`.

To run: call `installBench()` once from a dev entry point (temporary, do not commit), start
`npm run dev` in `web/`, open the page in a real browser, and run
`await __sadiLiveBench()` in the devtools console; pass the result through `meets60fps`. Record the
browser, hardware and numbers here once measured.

Dev proxy: `web/vite.config.ts` proxies `/api` with `ws: true` so `WS /api/stream` works under `vite dev`.

## Server-streamed drift, capture window and simulated flag

`state` messages carry `drift_vps`, `window` and `simulated`; `hello` carries `simulated`
(see [../server/websocket.md](../server/websocket.md)). `parseMessage` exposes them as
`driftVps`, `window` (`firstRawSeq`, `lastRawSeq`) and `simulated` (binary frames unchanged).
`useRunLive` folds them into `SideState`; `deriveLive` prefers the server drift over the
client-side estimate and the `simulated` prop falls back to the server flag.

## Auto-scaled y axis and idle readout (audit1 #17, #26)

`liveYRange` fits the y axis to the padded signal envelope (minimum span 1 mV). The
+-4.9 V saturation limits and shaded zones appear only once the signal nears them, when the
axis returns to the fixed +-5.5 V view. Axis and legend text uses larger fonts than the
default theme. `deriveLive` takes the age of the newest frame: older than 2 s the readout is
idle (no volts, no drift, motion unknown, no saturation) and capture is blocked, so a stopped
stream no longer shows stale SATURATED, "NaN mV/s" or Creeping.
