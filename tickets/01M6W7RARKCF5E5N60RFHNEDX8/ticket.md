+++
id = "01M6W7RARKCF5E5N60RFHNEDX8"
title = "Review screen: re-edit points, window edits, undo/redo, results recompute"
type = "task"
category = "in-progress"
priority = "high"
points = 5
parent = "01M6W7R0BA45XYP4MGXJ21Z778"
reporter = "lognd"
created = "2026-11-08T00:08:27Z"
updated = "2026-11-08T05:55:30Z"
idempotency_key = "sadi-f13"
labels = ["ws:web", "model:sonnet", "creates:web/src/screens/review/**", "creates:docs/web/review-screen.md"]
scope = ["web/src/screens/review/**", "docs/web/review-screen.md", "docs/web/plots.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R3KN3HXVMJQ1D3MJNBZY"

[[links]]
kind = "blocked-by"
target = "01M6W7R3TJETR6N3EVA9PMPWH8"

[[links]]
kind = "blocked-by"
target = "01M6W7R41EVGYTSV1B72ZQVKAB"

[[acceptance]]
text = "List/plot of captured points with settled/forced flags; edit averaging window, exclude/include, relabel weights; undo/redo history visible"
bound = true

[[acceptance]]
text = "Edits go through API as compensating events; plots and results update from raw recompute"
bound = true

[[acceptance]]
text = "Review screen unit tests (vitest) cover edits, undo/redo, recompute refresh and problem hints"
bound = true
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). TypeScript: strict mode, no any, ESLint + vitest clean.
