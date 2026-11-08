+++
id = "01M6W7RAH93KKNK1WH67KWS2S7"
title = "Live trace plot: scrolling binary-WebSocket trace with settle markers"
type = "task"
category = "done"
outcome = "done"
priority = "high"
points = 5
parent = "01M6W7R0BA45XYP4MGXJ21Z778"
reporter = "lognd"
created = "2026-11-08T00:08:27Z"
updated = "2026-11-08T05:48:01Z"
idempotency_key = "sadi-f4"
labels = ["ws:web", "plots", "model:sonnet", "creates:web/src/plots/live/**", "creates:web/src/ws/**", "creates:web/src/hooks/useTrace.ts", "creates:docs/web/live-trace.md"]
scope = ["web/src/plots/live/**", "web/src/ws/**", "web/src/hooks/useTrace.ts", "docs/web/live-trace.md", "docs/web/plots.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R383ZG0WZNNVJMQYWW87"

[[links]]
kind = "blocked-by"
target = "01M6W7R3ZPY606D3MHG4QRM2GS"

[[acceptance]]
text = "Decodes the binary frame spec from B5, scrolling window with min/max envelope, marks load changes, settle/capture events and saturation limits at +-4.9 V"
bound = true

[[acceptance]]
text = "Sustains 60 fps with 50 kS/s source in a browser benchmark test; reconnect handling shown in-plot"
bound = true

[[acceptance]]
text = "Screenshot-ready: titled, labelled axes with units, legend; export via F3"
bound = true
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). TypeScript: strict mode, no any, ESLint + vitest clean.
