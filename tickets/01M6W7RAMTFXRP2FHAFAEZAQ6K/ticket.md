+++
id = "01M6W7RAMTFXRP2FHAFAEZAQ6K"
title = "Weights and setup screens: inventory entry, group weighing, specimen, calibration inputs"
type = "task"
category = "todo"
priority = "high"
points = 5
parent = "01M6W7R0BA45XYP4MGXJ21Z778"
reporter = "lognd"
created = "2026-11-08T00:08:27Z"
updated = "2026-11-08T00:08:27Z"
idempotency_key = "sadi-f10"
labels = ["ws:web", "oq:Q7", "model:sonnet", "creates:web/src/screens/setup/**", "creates:web/src/screens/weights/**", "creates:docs/web/weights-screen.md"]
scope = ["web/src/screens/setup/**", "web/src/screens/weights/**", "docs/web/weights-screen.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R26WGJ0TZ4GS8N0YH4FG"

[[links]]
kind = "blocked-by"
target = "01M6W7R41EVGYTSV1B72ZQVKAB"

[[acceptance]]
text = "Table entry of numbered weights (mass, u_mass, height, u_height) with validation, group balance weighing entry, specimen dimensions and L0 defaults, enter-once persistence"
bound = false

[[acceptance]]
text = "Keyboard-friendly (tab/enter), inline derived values (combo masses), no field is ever asked twice"
bound = false
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). TypeScript: strict mode, no any, ESLint + vitest clean.
