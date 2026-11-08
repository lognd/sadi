# Calibration plot

Status: current

Owner ticket ~DDAPA9P. Code: `web/src/plots/calibration/`. Content rules: [live-view.md 7.3](../live-view.md).
Renderer: [plots.md](plots.md). This module contains no drawing code; it only builds core `Scene`s.

## API

- `buildCalibrationScenes(data, sizing?)` returns `Result<{main, residuals}, CalibrationPlotError>`
  (pure). Errors: `empty`, `length_mismatch`, `non_finite`, `missing_text`; none throw.
- `CalibrationPlot` (React) renders both scenes with `renderToCanvas`; it recomputes on every new
  `data` object, so each captured point redraws both panels. Export uses the core
  `exportFigure` on either scene.
- `CalibrationData`: captured `volts`/`height`, optional `height_u95` (error bars), sampled
  `fit_volts`/`fit_height`/`band_lower`/`band_upper`, `residuals`, and the API-formatted
  `equation` ('h = (m +/- U) V + (b +/- U)', class-rule sig figs) and `r2` strings, shown verbatim.

## Linked residuals

The main and residual scenes get the same fixed x range (data and fit extent plus 5 %), so
their plot areas line up. The residual scene draws residual points and a zero line.

## Generic core features added for this plot

- `Series.yErr`: symmetric error half-widths drawn as capped bars; the autoscaled y domain includes them.
- Annotation anchor `"auto"`: layout scores each corner by plotted vertices (series, fit, band
  edges; strided to at most ~2000 samples per curve) it would cover, rejects corners overlapping
  the legend, and picks the least-covered (ties: br, tr, bl, tl).

Decimation to pixel width, tick and precision choice, DPR scaling and export sizing are the
unchanged core behaviour.

## Tests

`web/src/plots/calibration/calibration.test.tsx` (mapping, error paths, live update, golden SVG
snapshots for both panels) and the error bar / auto anchor cases in `core/plots.test.ts`.
