# Front panel

Status: current

Parent: [wizard.md](wizard.md), [live-trace.md](live-trace.md). Code: `web/src/components/wizard/FrontPanel.tsx`,
`web/src/components/live/**`, `web/src/state/LiveContext.tsx`.

Every wizard step (setup, run, review, results, export) renders inside one LabVIEW-style panel:

- Left sidebar: `StepRail` with plain-language titles and blurbs, plus the shortcut list.
- Centre: the step content and the prominent next-action button.
- Centre top: the "Do this" card (`DoThisCard`, text in `stepGuide.ts`): 2-4 short imperative
  lines, a "Where to look" hint and "Step N of 7 - next: ...", then the single primary button.
- Right (sticky, below 64rem it stacks): `LiveTrace` (the live canvas) and the status bar.

## Instrument bar and debug strip (every page)

`App` renders `InstrumentBar` (sticky, under the header) and `DebugStrip` on every page,
including pre-session Setup. The bar shows big monospace LVDT volts, displacement and load
("not calibrated yet" until calibration and tare exist), drift, settle, signal, connection and a
loud SIMULATED banner. The strip shows device, firmware, sample rate, seq / durable seq, frame age,
backend, session id, data folder, save / WAL state and last error. A field the backend does not
expose reads "unavailable (reason)". Facts come from `useBackendFacts` (polls REST) and
`useTrace().meta` (per-frame seq, durable seq, arrival time). `App` calls `useBackendFacts` once and
passes the facts to both components. It retries the Doctor host facts (data folder) until known, and
polls `/api/session` only every 5th tick while no session is open. When the instrument is
disconnected the bar shows the device hint ("plug in the instrument") and "no signal" for Settle and
Signal (never "ok"). `App` also polls `/api/health` every 3 s: the pill and strip follow the backend
down and up; only the first failure opens the Doctor, and the wizard shows a backend-down notice
and reloads itself when the connection returns. The Doctor screen leads with a verdict banner
(verdict, counts, first action). The step rail follows the step content in DOM order (focus order).

## Shared live feed

`LiveProvider` (mounted once in `App`) calls `useRunLive` once, so Doctor, the wizard and the run
screen share one `/api/stream` subscription. Consumers call `useLive()`, which throws outside a
provider. The readout marks data stale in words ("(!) Stale - not current"); state is never colour only.

## Testing

`state/testLive.tsx` offers `fakeLive({view, side, conn})` and `withLive(el, live?)` to render
live-dependent components without a socket.

Data-safety text (for example "Captured cycles are never overwritten") is unchanged.
