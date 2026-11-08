+++
id = "01M6W7RATGKGPEYSMC5H8WGMBV"
title = "Results/Export screen: report view, figure export, CSV download"
type = "task"
category = "in-progress"
priority = "medium"
points = 3
parent = "01M6W7R0BA45XYP4MGXJ21Z778"
reporter = "lognd"
created = "2026-11-08T00:08:27Z"
updated = "2026-11-08T05:51:13Z"
idempotency_key = "sadi-f15"
labels = ["ws:web", "model:sonnet", "creates:web/src/screens/export/**", "creates:docs/web/export-screen.md"]
scope = ["web/src/screens/export/**", "docs/web/export-screen.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R383ZG0WZNNVJMQYWW87"

[[links]]
kind = "blocked-by"
target = "01M6W7R3Q5RVEC8YFA37P8582F"

[[links]]
kind = "blocked-by"
target = "01M6W7R3TJETR6N3EVA9PMPWH8"

[[links]]
kind = "blocked-by"
target = "01M6W7R41EVGYTSV1B72ZQVKAB"

[[acceptance]]
text = "Summary of final values with U and which settle value fed E, export-all-figures (PNG/SVG at chosen DPI), CSV download in the 32-column schema"
bound = false

[[acceptance]]
text = "Shows export provenance from DS7"
bound = false
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). TypeScript: strict mode, no any, ESLint + vitest clean.
