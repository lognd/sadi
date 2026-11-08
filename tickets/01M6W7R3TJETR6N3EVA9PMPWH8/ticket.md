+++
id = "01M6W7R3TJETR6N3EVA9PMPWH8"
title = "Results panel: best value +/- U, 95% interval, plain-language confidence"
type = "task"
category = "in-progress"
priority = "high"
points = 5
parent = "01M6W7R0BA45XYP4MGXJ21Z778"
reporter = "lognd"
created = "2026-11-08T00:08:20Z"
updated = "2026-11-08T03:39:05Z"
idempotency_key = "sadi-f8"
labels = ["ws:web", "model:sonnet", "creates:web/src/components/results/**", "creates:docs/web/results-panel.md"]
scope = ["web/src/components/results/**", "docs/web/results-panel.md", "docs/index.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R0R9PGCDJWAD321F3H53"

[[links]]
kind = "blocked-by"
target = "01M6W7R23Q44RD6WVCBGKVPN2E"

[[links]]
kind = "blocked-by"
target = "01M6W7R3J00J2HQ7XPW19WDD6Q"

[[acceptance]]
text = "Always-visible panel: calibration slope/intercept, tare, E, r^2, yield each as value +/- U (3 s.f. / 2 s.f.), standard uncertainty, 95% interval and confidence sentence, updating after every captured point"
bound = true

[[acceptance]]
text = "Shows which settle value fed E; flags RSS vs Monte Carlo disagreement; copy-to-clipboard of values with units"
bound = true

[[acceptance]]
text = "Component tests incl. sig-fig rendering (display only, formatting source of truth is the API from SF1)"
bound = false
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). TypeScript: strict mode, no any, ESLint + vitest clean.
