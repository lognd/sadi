# Plot renderer core

Status: current

Owner ticket ~MQYWW87. Code: `web/src/plots/core/` (import from `index.ts`) and the theme in
`web/src/plots/theme.ts`. Content rules (titles, legend entries, annotation strings) live in
[live-view.md section 7](../live-view.md); this file documents the API that carries them. Plot
tickets (calibration, creep, stress-strain, live trace, export screen) only build a `Scene`.

## Pipeline

```
Scene (pure data) -> computeLayout -> Layout (geometry, once)
                  -> buildDrawList -> DrawOp[] (backend-neutral primitives)
                       |-> executeDrawList -> canvas (screen, DPR scaled)
                       |-> executeDrawList -> offscreen canvas -> PNG (dpi scaled)
                       `-> drawListToSvg   -> SVG text
```

Layout is computed in CSS pixels with a deterministic text-width estimate (no font probing), so
screen, PNG and SVG are identical up to a uniform scale. No dependency was added.

## Scene

- `width`, `height` (CSS px), `title`, optional `subtitle`, `footer` (coverage statement).
- `xAxis`, `yAxis`: `{label, unit?, min?, max?}`; rendered "label (unit)". Omitted bounds come
  from the data and snap to nice 1/2/5 ticks. Linear scales only.
- `series[]`: `{id, label, x, y, style: "line"|"points", marker?: "filled"|"ring"|"cross",
  color?, dashed?}`; `x`/`y` are arrays or typed arrays.
- `bands[]`: `{id, label, x, lower, upper, color?}` shaded confidence band.
- `fits[]`: `{id, label, x, y, color?}` dashed fit line (supply two or more sampled points).
- `annotation`: `{lines, anchor?: tl|tr|bl|br}` boxed equations and values (default `br`; legend
  sits top right and an annotation at `tr` stacks below it).
- `legend` (default on; one row per series, band and fit), `theme` (`lightTheme`).

## Rendering and export

- `renderToCanvas(canvas, scene, {dpr?})` sizes the backing store by device pixel ratio.
- Lines, bands and fits are min/max decimated per plot pixel (`decimateIndices`), at most
  2*width + 2 vertices for any input size (100k points tested). Extremes are preserved.
- `exportFigure(scene, {format: "png"|"svg", dpi?}, deps?)` returns
  `{ok: true, value: {blob, mime, width, height, text?}}` or `{ok: false, error}`. PNG pixel size
  is scene size x dpi/96 (300 dpi gives 3.125x); SVG is vector and also returns `text`.
  `deps.createCanvas` injects an offscreen canvas (tests, workers).

## Tests

`web/src/plots/core/plots.test.ts` covers tick choice and formatting, layout determinism,
decimation bounds, an SVG snapshot, a recorded 2D-context call snapshot, and PNG export. Real
PNG golden images are not used: jsdom and the `canvas` package are not installed, so goldens are
taken at the draw-call level (a recording `Ctx2D`), and the test asserts that 96 dpi and 300 dpi
exports issue identical calls apart from the scale factor. Update snapshots deliberately with
`vitest -u`.
