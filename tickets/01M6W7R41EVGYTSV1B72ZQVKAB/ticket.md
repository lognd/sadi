+++
id = "01M6W7R41EVGYTSV1B72ZQVKAB"
title = "Wizard shell: step rail, next-action panel, status bar, keyboard capture"
type = "task"
category = "in-progress"
priority = "high"
points = 8
parent = "01M6W7R0BA45XYP4MGXJ21Z778"
reporter = "lognd"
created = "2026-11-08T00:08:20Z"
updated = "2026-11-08T05:37:19Z"
idempotency_key = "sadi-f9"
labels = ["ws:web", "model:sonnet", "creates:web/src/components/wizard/**", "creates:web/src/components/status/**", "creates:web/src/keys/**", "creates:docs/web/wizard.md"]
scope = ["web/src/components/wizard/**", "web/src/components/status/**", "web/src/keys/**", "docs/web/wizard.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R0R9PGCDJWAD321F3H53"

[[links]]
kind = "blocked-by"
target = "01M6W7R23Q44RD6WVCBGKVPN2E"

[[links]]
kind = "blocked-by"
target = "01M6W7R335N9GPFD4DYXP2D6HY"

[[links]]
kind = "blocked-by"
target = "01M6W7R3XY1B0BF689RX3H80G2"

[[acceptance]]
text = "Persistent step rail (Setup, Weights, Calibrate, Tare, Elastic, Plastic, Results, Export) from API wizard state, big next-action panel, status bar (connected/simulated, settled/creeping, saturation light), errors rendered with their 'what to do' hint"
bound = true

[[acceptance]]
text = "Keyboard: one key accepts the capture (Space/Enter), Ctrl+Z / Ctrl+Y undo/redo, arrows nudge window; shortcuts listed on screen"
bound = true

[[acceptance]]
text = "Implements wireframes in docs/ux.md; component and keyboard tests"
bound = false
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). TypeScript: strict mode, no any, ESLint + vitest clean.
