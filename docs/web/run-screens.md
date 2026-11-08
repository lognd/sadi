# Run screens (calibrate, tare, elastic, plastic)

Status: current

Parent: [wizard.md](wizard.md), [live-trace.md](live-trace.md). Code: `web/src/screens/run/**`.

## Behaviour

One `RunScreen` serves all four capture phases (`phases.ts`). It holds a single stream
subscription: `useRunLive` wraps `useTrace`'s injectable `open` and taps `state` and `result`
messages, so there is no second socket. `TraceCanvas` draws the shared live scene.

- Big readout: `Live V: 1.2345 V [Settled]` or `[Creeping N mV/s]`, via `settleText`.
- Capture: the accept key (Space) posts `POST /api/session/points` (`capture.ts`).
  `decide` is the single rule table: Space never fires while Creeping, Saturated or
  Disconnected. Shift+Space asks for confirmation, then records the point as unsettled
  (`settled: false`, `forced_early: true`).
- Saturation: above 4.9 V in the recent envelope the view shows a warning, the status bar signal
  reads SATURATED, and capture is blocked even when forced.
- Disconnect: Source becomes Disconnected, the readout is marked stale, capture is paused and a
  notice states that saved data is untouched. Capture resumes on reconnect.
- Per-phase plot: calibrate uses `CalibrationPlot`, elastic and plastic use
  `StressStrainScreen`, tare has none. The payload is a host prop.

## Gaps (filed as tickets)

- G1: the stream carries no live drift rate, capture-window raw seq or simulated flag. Drift is
  estimated client-side from the trace and the simulated flag is a prop.
- G2: no endpoint serves per-phase plot data, hence the host prop.
- F3 export is not offered by the run screen's trace.

## Tests

`web/src/screens/run/RunScreen.test.tsx` feeds mocked sim-like TRACE frames and state texts
through the real decoder, `TraceWindow` and `foldSide`. A real-browser sim run is a follow-up.
