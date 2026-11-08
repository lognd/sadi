# Stress-strain plot

Status: current

Owner ticket ~3MJNBZY. Code: `web/src/plots/stressstrain/`. Built on the shared renderer core
([plots.md](plots.md)); this module only builds a core `Scene` and never draws itself.

## Data contract

`StressStrainData` (`model.ts`) mirrors `python/sadi/labs/lctt` (`CurvePoint`, `ModulusFit`,
`YieldResult`): points (strain, stress MPa, 1-sigma uncertainties, settle source, saturated), the
E fit (window, modulus, intercept, E in GPa with U95, r^2, `display` string from the API), and the
offset yield.

## Scene mapping (`buildStressStrainScene`)

- Points: filled markers; forced-early points as rings; saturated points as crosses.
- Uncertainty bars: two-point line series per point and axis (core has no bar primitive yet).
- Fit window: a shaded band spanning the window strains. E fit: dashed fit line. 0.2 % offset
  line: dashed fit line of slope E from the offset strain. Yield: ringed marker.
- Annotation: API `display` text, else `E = ... +/- ... GPa, r^2 = ...`, anchored bottom right.
- Footer carries the saturation, forced-early and low-r^2 warnings. Legend is off.

All decimation, ticks, precision, DPR scaling and PNG/SVG export come from the core; nothing here
is plot-specific drawing. Gaps needing generic core support (error bars, annotation collision
avoidance, incremental live redraw) are filed as a follow-up ticket against `web/src/plots/core/**`.

## Window selection

Pure logic in `selection.ts` (`clampWindow`, `setEdge`, `keyStep`, `dragWindow`; minimum 3 points).
`StressStrainPlot` adds pointer drag (nearest edge), arrow/Home/End keys on the focused group
(`[` and `]` switch edge, Shift steps by 5) and two range inputs. Each committed change calls
`onWindowChange`, which the host wires to the API refit; the results panel updates from the reply.

## Tests

`stressstrain.test.ts`: selection logic, scene mapping, and an SVG golden snapshot.
