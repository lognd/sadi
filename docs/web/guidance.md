# Guidance panel

Status: current

Parent: [web layout](../web-layout.md), next to the [budget panel](budget-panel.md). Server side:
[results, guidance](../server/results.md); push hint: `guidance` message in
[websocket](../server/websocket.md).

- `components/guidance/GuidancePanel.tsx`: presentational; takes a `GuidanceState` (or null)
  and renders the next step ("Use weights 3, 5, 6" plus the suggested load), the expected value
  with unit, points taken, a confidence meter, and an inline-editable target.
- Meter: `role="meter"` with `aria-valuemin/max/now` (percent of the way to the target, from
  `confidence.fraction`) and `aria-valuetext` giving the relative half-width. The target field
  takes a percentage; invalid input shows an alert and is not sent. A valid value (blur or
  Enter) calls `onTargetChange(fraction)`; the host refetches with `?target=`.
- Stop-early banner (`role="status"`): shown when `stop_early` or `run_complete_proposed`.
  It is advisory only. The button (or key `N` while the panel has focus, `handleAdvanceKey`)
  calls `onAdvance`; the panel never advances anything itself and the user may ignore it.
  Without `onAdvance` no button is rendered.
- GP load panel (`components/guidance/GpLoadPanel.tsx`, embedded in `GuidancePanel`): shows the
  recommended next load in kg and N, expected gain (`expected_gain`, percent narrower), expected
  half-width after the point, up to 3 `alternatives` as one-click buttons (`onPickLoad(kg)`), and
  an advisory `gp_state` note (collecting, enough, diminishing, unreliable). Numbers use tabular
  numerals. When `gp_state` is empty or absent it shows the even-schedule text instead. See
  [LCTT GP selector](../labs/lctt-gp-selector.md). `GuidancePanel` also takes `status`
  (`loading` / `error`) plus `error` for the loading and error states.
- `components/guidance/api.ts`: `getGuidance({phase, hold, target}, fetcher)` calls
  `GET /api/results/guidance` with an injectable fetcher; errors (409 no session, 422 bad
  input) come back as an http error Result.
- `components/guidance/types.ts` mirrors `GuidanceState` in `sadi/labs/lctt/guidance.py`.
- The WS `guidance` message currently carries no payload (`parseMessage` yields
  `{kind: "guidance"}`); a host should refetch via `getGuidance` when it arrives.

See also the [Results/Export screen](export-screen.md).
