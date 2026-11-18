# Review screen

Status: current

Parent: [plots and screens](plots.md), [web layout](../web-layout.md). Server side:
session edit/undo/redo in [api](../server/api.md) and [app](../server/app.md); recompute via
`GET /api/results` in [results](../server/results.md); `hello`/`result` stream messages in
[websocket](../server/websocket.md). Related: [results panel](results-panel.md), [wizard](wizard.md).

## What it does

- `screens/review/ReviewScreen.tsx` lists captured points (`GET /api/session/points`) with
  phase, flags (settled, forced early, excluded), inputs and edit count. `settled` and
  `forced_early` are shown when the server sends them (they are optional in `types.ts`).
- Per point: Exclude / Include; Edit opens `PointEditor` with the averaging window
  (first/last raw seq and sample, `set_window`) and an input relabel (`override_input`, for
  example weights). With a point selected, the wizard keys `[` `]` `{` `}` nudge the window
  start/end one sample (via `nudgeEdit`).
- Undo / Redo buttons and Ctrl+Z / Ctrl+Y use the existing keymap (`keys/useKeyCapture`);
  no separate listener. `History` lists done and undone actions.
- After every accepted write the screen reloads points, history and `GET /api/results` (raw
  recompute) and shows the `ResultsPanel`. If results are unavailable it says so.

## Data safety

Edits are never destructive. The server appends compensating records, durable before the
response; undo and redo are themselves compensating edits and the original captured data is
retained. The screen states this on screen (`SAFETY_NOTE`). A refused edit leaves the
displayed data unchanged.

## Errors

Failures are `application/problem+json`; `describeProblem` shows title, detail and the `hint`.
Network errors and non-JSON bodies get a plain message.

## Structure

`api.ts` (injectable-fetch calls), `session.ts` (`loadReview`, `runAction`), `types.ts`
(mirrors of `PointView`, including the server-sent `settled` and `forced_early` flags, `History`, `Committed`, problem body). No plot code was added.

## Layout and provenance (Audit1 #27, #36)

Results are shown first, above the point table. Tables sit in a horizontally scrolling wrapper so nothing clips at 800 px. Long point ids are shortened (full id in the tooltip). Numbers are rounded to 4 significant figures.

## Exclusions in export and plots

Excluding any point (calibration, tare, specimen or load) removes it from the
fit used by the results, the calibration plot and the LCTT CSV, so all three
agree. Nothing is deleted: the point and the exclusion stay in the WAL, and an
excluded load point is still written to the CSV with `excluded` set.
