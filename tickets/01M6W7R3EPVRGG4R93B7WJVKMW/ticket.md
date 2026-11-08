+++
id = "01M6W7R3EPVRGG4R93B7WJVKMW"
title = "Creep plot: strain vs log-time per hold with fit and slip markers"
type = "task"
category = "in-progress"
priority = "medium"
points = 3
parent = "01M6W7R0BA45XYP4MGXJ21Z778"
reporter = "lognd"
created = "2026-11-08T00:08:20Z"
updated = "2026-11-08T03:54:47Z"
idempotency_key = "sadi-f7"
labels = ["ws:web", "plots", "model:sonnet", "creates:web/src/plots/creep/**", "creates:docs/web/creep-plot.md"]
scope = ["web/src/plots/creep/**", "docs/web/creep-plot.md", "docs/web/plots.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R257EXZX1RD7VT3M5GJG"

[[links]]
kind = "blocked-by"
target = "01M6W7R383ZG0WZNNVJMQYWW87"

[[acceptance]]
text = "Strain vs log10(time since load) per hold, fit line with equation annotation, detected slip steps marked, settle threshold shown"
bound = true

[[acceptance]]
text = "Golden-image test with creeping and slipping simulator fixtures"
bound = false
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). TypeScript: strict mode, no any, ESLint + vitest clean.
