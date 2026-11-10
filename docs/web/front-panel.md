# Front panel

Status: current

Parent: [wizard.md](wizard.md), [live-trace.md](live-trace.md). Code: `web/src/components/wizard/FrontPanel.tsx`,
`web/src/components/live/**`, `web/src/state/LiveContext.tsx`.

Every wizard step (setup, run, review, results, export) renders inside one LabVIEW-style panel:

- Left sidebar: `StepRail` with plain-language titles and blurbs, plus the shortcut list.
- Centre: the step content and the prominent next-action button.
- Right (sticky, below 64rem it stacks): `LiveReadout` (LVDT volts, drift, settle state, signal,
  connection, and a SIMULATED banner when the source is simulated), `LiveTrace` (the live
  canvas) and the status bar.

## Shared live feed

`LiveProvider` (mounted once in `App`) calls `useRunLive` once, so Doctor, the wizard and the run
screen share one `/api/stream` subscription. Consumers call `useLive()`, which throws outside a
provider. The readout marks data stale in words ("(!) Stale - not current"); state is never colour only.

## Testing

`state/testLive.tsx` offers `fakeLive({view, side, conn})` and `withLive(el, live?)` to render
live-dependent components without a socket.

Data-safety text (for example "Captured cycles are never overwritten") is unchanged.
