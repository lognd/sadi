+++
id = "01M6W7R432XQSR47M3W61M215J"
title = "Uncertainty budget and formula panel: dominant input, rendered LaTeX derivation"
type = "task"
category = "todo"
priority = "medium"
points = 5
parent = "01M6W7R0BA45XYP4MGXJ21Z778"
reporter = "lognd"
created = "2026-11-08T00:08:20Z"
updated = "2026-11-08T00:08:20Z"
idempotency_key = "sadi-f17"
labels = ["ws:web", "uncertainty", "model:sonnet", "creates:web/src/components/budget/**", "creates:docs/web/budget-panel.md"]
scope = ["web/src/components/budget/**", "docs/web/budget-panel.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R2BS0R89GW39HM0XPX0J"

[[links]]
kind = "blocked-by"
target = "01M6W7R3TJETR6N3EVA9PMPWH8"

[[links]]
kind = "blocked-by"
target = "01M6W7R3XY1B0BF689RX3H80G2"

[[acceptance]]
text = "Shows the ranked uncertainty budget per result (bar chart + table) and highlights the dominant input; click a result to see its formula and derivation rendered from `.latex`"
bound = false

[[acceptance]]
text = "KaTeX (or equivalent) dependency added via a package.json lease widen; component tests with fixture budgets"
bound = false
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). TypeScript: strict mode, no any, ESLint + vitest clean.
