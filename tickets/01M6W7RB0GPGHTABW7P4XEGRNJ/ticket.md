+++
id = "01M6W7RB0GPGHTABW7P4XEGRNJ"
title = "Results-stream client: version/stale marker and refinement progress in the UI"
type = "task"
category = "todo"
priority = "high"
points = 3
parent = "01M6W7R0BA45XYP4MGXJ21Z778"
reporter = "lognd"
created = "2026-11-08T00:08:27Z"
updated = "2026-11-08T00:08:27Z"
idempotency_key = "sadi-f16"
labels = ["ws:web", "ws:conc", "model:sonnet", "creates:web/src/results-stream/**", "creates:docs/web/results-stream.md"]
scope = ["web/src/results-stream/**", "docs/web/results-stream.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R0R9PGCDJWAD321F3H53"

[[links]]
kind = "blocked-by"
target = "01M6W7R3TJETR6N3EVA9PMPWH8"

[[links]]
kind = "blocked-by"
target = "01M6W7RAK3KCB1G87VKETJKV0D"

[[acceptance]]
text = "Subscribes to the versioned results stream; each number renders with a stale marker when its version lags and a progress indicator while MC/GP refine (interval visibly tightening)"
bound = false

[[acceptance]]
text = "Never displays a result older than the latest data version without the marker; component tests with mocked streams"
bound = false
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). TypeScript: strict mode, no any, ESLint + vitest clean.
