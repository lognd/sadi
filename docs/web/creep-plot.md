# Creep plot

Status: current

Owner ticket ~7WJVKMW. Code: `web/src/plots/creep/`. Fit model: [lctt/creep.md](../lctt/creep.md).
Renderer: [plots.md](plots.md). This module contains no drawing code; it only builds a core `Figure`.

## API

- `buildCreepScene(data, sizing?)` returns `Result<Figure, CreepPlotError>` (pure). Errors: `empty`,
  `length_mismatch`, `non_finite`, `non_positive_time`; none throw.
- `CreepPlot` (React) renders the figure with `renderToCanvas`; export uses core `exportFigure`.
- `CreepData.holds[]`: `t` (seconds since load, > 0), `strain`, optional `fit` (`a`, `b`, `b_se`, `r2`),
  `slips[]` (`t`, `strain`, `size_mm`), optional `settle_band` (`lower`, `upper` strain).

## Layout

One panel per hold, stacked, sharing a log10 time axis (`AxisSpec.scale = "log"`). Each panel shows
strain points, the dashed fit `strain = a + b ln(t)` (log-spaced samples) with an annotation
(`b` with its standard error, `r^2`), a cross marker plus "slip X mm" label per detected slip, and
the settle threshold as a shaded y span. A hold without a fit is annotated "no fit (hold too short)".

## Tests

`web/src/plots/creep/creep.test.tsx`: structure, error cases, and a golden SVG snapshot of a creeping
and a slipping hold (`vitest -u` to update).
