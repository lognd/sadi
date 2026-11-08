+++
id = "01M6W7R3KN3HXVMJQ1D3MJNBZY"
title = "Stress-strain plot: live E fit, selectable window, 0.2% offset yield"
type = "task"
category = "in-progress"
priority = "high"
points = 5
parent = "01M6W7R0BA45XYP4MGXJ21Z778"
reporter = "lognd"
created = "2026-11-08T00:08:20Z"
updated = "2026-11-08T03:46:09Z"
idempotency_key = "sadi-f6"
labels = ["ws:web", "plots", "model:sonnet", "creates:web/src/plots/stressstrain/**", "creates:docs/web/stress-strain-plot.md"]
scope = ["web/src/plots/stressstrain/**", "docs/web/stress-strain-plot.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R383ZG0WZNNVJMQYWW87"

[[links]]
kind = "blocked-by"
target = "01M6W7R3BBDEXG9CPYWTQ7ZKZW"

[[acceptance]]
text = "Points with uncertainty bars, draggable/keyboard-adjustable fit window shading, E fit line with annotation 'E = ... +/- ... GPa, r^2 = ...', 0.2% offset line and yield marker, forced-early points marked distinctly"
bound = true

[[acceptance]]
text = "Window changes call the API and results panel updates; golden-image test"
bound = true
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). TypeScript: strict mode, no any, ESLint + vitest clean.
