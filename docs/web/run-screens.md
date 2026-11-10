# Run screens (calibrate, tare, elastic, plastic)

Status: current

Parent: [wizard.md](wizard.md), [live-trace.md](live-trace.md). Code: `web/src/screens/run/**`.

## Behaviour

One `RunScreen` serves all four capture phases (`phases.ts`). It holds a single stream
subscription: `useRunLive` wraps `useTrace`'s injectable `open` and taps `state` and `result`
messages, so there is no second socket. `TraceCanvas` draws the shared live scene.

- Readout: the big volts, drift and settle state now live in the app-level `InstrumentBar`
  (see [front-panel.md](front-panel.md)); `settleText` stays in `components/live/settle.ts`.
- Capture: the accept key (Space) posts `POST /api/session/points` (`capture.ts`).
  `decide` is the single rule table: Space never fires while Creeping, Saturated or
  Disconnected. Shift+Space asks for confirmation, then records the point as unsettled
  (`settled: false`, `forced_early: true`).
  Each accept attempt sends a stable `request_id`, reused on retry until it succeeds. A held key (auto-repeat) never re-accepts, and after a successful capture a further accept is refused until the load change is marked.
- Saturation: above 4.9 V in the recent envelope the view shows a warning, the status bar signal
  reads SATURATED, and capture is blocked even when forced.
- Disconnect: Source becomes Disconnected, the readout is marked stale, capture is paused and a
  notice states that saved data is untouched. Capture resumes on reconnect.
- Per-phase plot: calibrate uses `CalibrationPlot`, elastic and plastic use
  `StressStrainScreen`, tare has none. The payload is a host prop.

- Export: F3 (resolved by `resolveKey` to `export`) downloads `GET /api/export/{format}`
  (`exportTrace.ts`, default `lctt-csv`, prop `exportFormat`). Failures show in the status line.

A "Mark load change" button (`loadChange.ts`) POSTs /api/session/load-change so the settle
detector can settle after a load is applied. The sim banner also shows when the stream hello
reports `simulated`.

## Capture inputs

`inputFields.ts` defines the per-phase fields (SI units, mirroring `parse_inputs`): calibrate
volts + gauge height (m); tare mean volts + n (+ optional sd); elastic and plastic volts +
total hanging mass (kg) (+ optional mass uncertainty). Blank volts/mean means "use the live
block-mean reading" (shown as the placeholder and recorded). Required fields are never
defaulted: `collectInputs` refuses with one clear message per problem before any POST, and a
backend 422 body is shown in the status line. Typed values persist between points. Hotkeys are
ignored while a field has focus (typing never captures); a hint under the inputs says so
(`TEXT_FIELD_HOTKEY_HINT`, linked via `aria-describedby`), and Esc blurs the field so hotkeys resume
(Tab also works).

## Gaps (filed as tickets)

- G1: the stream carries no live drift rate, capture-window raw seq or simulated flag. Drift is
  estimated client-side from the trace and the simulated flag is a prop.
- G2: no endpoint serves per-phase plot data, hence the host prop.

## Tests

`web/src/screens/run/RunScreen.test.tsx` feeds mocked sim-like TRACE frames and state texts
through the real decoder, `TraceWindow` and `foldSide`. A real-browser sim run is a follow-up.
