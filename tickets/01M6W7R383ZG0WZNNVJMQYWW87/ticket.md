+++
id = "01M6W7R383ZG0WZNNVJMQYWW87"
title = "Plot renderer core: publication-quality canvas, annotations, one-click PNG/SVG export"
type = "task"
category = "todo"
priority = "high"
points = 8
parent = "01M6W7R0BA45XYP4MGXJ21Z778"
reporter = "lognd"
created = "2026-11-08T00:08:19Z"
updated = "2026-11-08T00:08:19Z"
idempotency_key = "sadi-f3"
labels = ["ws:web", "plots", "model:sonnet", "creates:web/src/plots/core/**", "creates:web/src/plots/theme.ts", "creates:docs/web/plots.md"]
scope = ["web/src/plots/core/**", "web/src/plots/theme.ts", "docs/web/plots.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R0R9PGCDJWAD321F3H53"

[[links]]
kind = "blocked-by"
target = "01M6W7R2S1S08W0QG20KR3SSE1"

[[acceptance]]
text = "Canvas renderer (uPlot-like performance, 100k points) with title, axis labels with units, legend, confidence bands, fit lines, annotation box with equations and values, nice tick formatting, light theme, device-pixel-ratio aware"
bound = false

[[acceptance]]
text = "exportFigure(format: png|svg, dpi) renders from the SAME scene description at high DPI (e.g. 300) with identical layout; golden-image tests (png) and SVG snapshot tests"
bound = false

[[acceptance]]
text = "Scene API documented so F4-F7 only supply data and annotations"
bound = false
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). TypeScript: strict mode, no any, ESLint + vitest clean.
