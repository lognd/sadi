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
  from the data and snap to nice 1/2/5 ticks. `scale?: "linear"|"log"` (default linear); a log axis uses decade
  ticks (1, 2, 5 within two decades, strided past seven) and needs positive data.
- `series[]`: `{id, label, x, y, style: "line"|"points", marker?: "filled"|"ring"|"cross",
  color?, dashed?}`; `x`/`y` are arrays or typed arrays.
- `bands[]`: `{id, label, x, lower, upper, color?}` shaded confidence band.
- `fits[]`: `{id, label, x, y, color?}` dashed fit line (supply two or more sampled points).
- `annotation`: `{lines, anchor?: tl|tr|bl|br}` boxed equations and values (default `br`; legend
  sits top right and an annotation at `tr` stacks below it).
- `annotations[]`: further `AnnotationBox`es. A fixed anchor is tried first, then the other corners.
- `markers[]`: `{id, x, y, kind: "filled"|"ring"|"cross", color?, label?}` point markers; a label
  is placed beside the marker. `labels[]`: `{id, x, y, text}` free text tied to a data point.
- `spans[]`: `{id, axis: "x"|"y", from, to, color?}` shaded bands across the whole plot.
- `xLabels: false` hides x tick labels and title; `plotLeft` sets a minimum left plot edge.
  Both exist so stacked panels line up.
- `legend` (default on; one row per series, band and fit), `theme` (`lightTheme`).

## Rendering and export

- `renderToCanvas(canvas, scene, {dpr?})` sizes the backing store by device pixel ratio.
- Lines, bands and fits are min/max decimated per plot pixel (`decimateIndices`), at most
  2*width + 2 vertices for any input size (100k points tested). Extremes are preserved.
- `exportFigure(scene, {format: "png"|"svg", dpi?}, deps?)` returns
  `{ok: true, value: {blob, mime, width, height, text?}}` or `{ok: false, error}`. PNG pixel size
  is scene size x dpi/96 (300 dpi gives 3.125x); SVG is vector and also returns `text`.
  `deps.createCanvas` injects an offscreen canvas (tests, workers).

Added later: `Series.yErr` (error bars) and annotation anchor `"auto"` (collision avoidance), see
[calibration-plot.md](calibration-plot.md).

## Accessibility: palette and non-colour cues

Owner ticket ~9NEG3KJ. Every `lightTheme.palette` colour is at least 3:1 against the plot
background (WCAG ratio via `web/src/a11y/contrast.ts`); the amber and sky entries were darkened
to meet it. Colour alone never identifies a series: `seriesCue(series, index)` in `core/scene.ts`
gives each series a default marker glyph (filled, ring, cross, cycling) and odd-indexed line
series a dashed stroke, unless the series sets `marker`/`dashed` itself. Drawing and the legend
both use it, so all plots inherit the cues. `web/src/plots/a11y-palette.test.ts` checks contrast and
simulates deuteranopia/protanopia (Machado matrices, CIE76 deltaE >= 10 or a differing cue).

## Label placement

Primary annotation, extra annotations, then marker and point labels go through one greedy,
deterministic placer (`placeBoxes`): requests are handled in order, each tries its candidates in a
fixed order (first wins ties), and every placed box becomes an obstacle for the next. Penalties:
overlap with the legend or a placed box, leaving the plot, and plotted vertices under the box.
Labels try rings of 8 positions at growing distance. The primary annotation keeps a fixed anchor.

## Log axes and validation

`validateScene(scene)` and `validateDrawable(d)` return `Result`-style `{ok, value|error}` with a
`PlotError` (`non_positive`, `bad_bounds`, `no_panels`); `describePlotError` formats it.
`exportFigure` validates first and returns `{ok: false, error}` instead of drawing garbage.
Without validation, layout ignores non-positive log bounds and projection drops non-finite points.

## Sub-panels (Figure)

`Figure {width, height, title, subtitle?, footer?, xAxis, panels[], theme}` where a `Panel` has
`{id, weight?, yAxis, series, bands?, fits?, annotation(s)?, markers?, labels?, spans?, legend?}`.
`figureScenes(fig)` splits it into one `Scene` per panel: heights follow weights, the x range is
the union over all panels, plot areas share one left edge, only the first panel has the title and
only the last shows x labels and the footer. `renderPlan(drawable)` builds the single draw list
(panels offset vertically); `renderToCanvas`, `paintScene`, `sceneToSvg` and `exportFigure` accept
a `Scene` or a `Figure`. `buildCalibrationScenes` is unchanged and still returns two scenes.

## Zoom and resize

`decimateWindow(x, y, buckets, x0, x1)` keeps in-window points plus one neighbour per side and
min/max decimates over the window. The draw list uses it with the x axis domain (`visibleIndices`),
so `zoomScene(scene, {xMin, xMax, width?, height?})` re-derives the decimation from the full data
with no precomputed pyramid.

## Tests

`web/src/plots/core/features.test.ts` covers placement, log axes, validation, zoom decimation,
figure panels and goldens for markers/spans/labels/figures (`vitest -u` to update).
`web/src/plots/core/plots.test.ts` covers tick choice and formatting, layout determinism,
decimation bounds, an SVG snapshot, a recorded 2D-context call snapshot, and PNG export. Real
PNG golden images are not used: jsdom and the `canvas` package are not installed, so goldens are
taken at the draw-call level (a recording `Ctx2D`), and the test asserts that 96 dpi and 300 dpi
exports issue identical calls apart from the scale factor. Update snapshots deliberately with
`vitest -u`.

## Plot modules

- [Stress-strain plot](stress-strain-plot.md)
- [Creep plot](creep-plot.md)
- [Live trace plot](live-trace.md)

## Screens

- [Review screen](review-screen.md) (edit captured points, undo/redo, results recompute)
