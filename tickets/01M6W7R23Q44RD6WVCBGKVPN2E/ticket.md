+++
id = "01M6W7R23Q44RD6WVCBGKVPN2E"
title = "UX design doc: wizard flow, step rail, wireframes (ASCII), keyboard map"
type = "docs"
category = "done"
outcome = "done"
priority = "high"
points = 8
parent = "01M6W7R0BA45XYP4MGXJ21Z778"
reporter = "lognd"
created = "2026-11-08T00:08:18Z"
updated = "2026-11-08T00:48:34Z"
idempotency_key = "sadi-f0"
labels = ["ws:web", "design", "model:fable", "creates:docs/ux.md"]
scope = ["docs/ux.md", "docs/index.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R0HZCA3MXA7231DQHSR7"

[[links]]
kind = "blocked-by"
target = "01M6W7R1G903HZ7V7JRCYC6ZT7"

[[acceptance]]
text = "Single-app wizard with persistent step rail Setup > Weights > Calibrate > Tare > Elastic > Plastic > Results > Export, big next-action panel, minimal modes; ASCII wireframes for every step and the review screen"
bound = true

[[acceptance]]
text = "Keyboard map (one key to accept capture, undo/redo, window nudge), status model (connected/simulated, settled/creeping, saturation) and error-message style ('what to do'), light theme, accessibility notes"
bound = true

[[acceptance]]
text = "In-and-out-in-minutes flow: time budget per phase and which defaults skip questions; how the confidence indicator and stop-early recommendation are shown without taking control from the user"
bound = true

[[acceptance]]
text = "Usability-pass protocol (task scripts, success criteria, issue log format) used by F14"
bound = true
+++

Fable ticket. Design before any screen code.

Suggested model: Fable.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001).
