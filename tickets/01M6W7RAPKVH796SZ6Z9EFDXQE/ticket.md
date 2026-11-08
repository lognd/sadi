+++
id = "01M6W7RAPKVH796SZ6Z9EFDXQE"
title = "Guidance UI: next-step panel, confidence meter, stop-early recommendation"
type = "task"
category = "done"
outcome = "done"
priority = "high"
points = 5
parent = "01M6W7R0BA45XYP4MGXJ21Z778"
reporter = "lognd"
created = "2026-11-08T00:08:27Z"
updated = "2026-11-08T05:50:54Z"
idempotency_key = "sadi-f12"
labels = ["ws:web", "model:sonnet", "creates:web/src/components/guidance/**", "creates:docs/web/guidance.md"]
scope = ["web/src/components/guidance/**", "docs/web/guidance.md", "docs/web/budget-panel.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R2S1S08W0QG20KR3SSE1"

[[links]]
kind = "blocked-by"
target = "01M6W7R3W8RJPVS0VVDG2YNMJB"

[[links]]
kind = "blocked-by"
target = "01M6W7R41EVGYTSV1B72ZQVKAB"

[[acceptance]]
text = "Next step shown as 'Use weights 3, 5, 6' with expected height/load; running 'confidence is enough' meter (CI half-width vs user-set target, editable inline)"
bound = true

[[acceptance]]
text = "Stop-early recommendation banner with one-key 'move to next phase' that the user may ignore; never auto-advances"
bound = true

[[acceptance]]
text = "Component tests with mocked guidance payloads"
bound = true
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). TypeScript: strict mode, no any, ESLint + vitest clean.
