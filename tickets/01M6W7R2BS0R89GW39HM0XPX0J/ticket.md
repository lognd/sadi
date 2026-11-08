+++
id = "01M6W7R2BS0R89GW39HM0XPX0J"
title = "Sensitivity coefficients and uncertainty budget (per-input contribution)"
type = "task"
category = "done"
outcome = "done"
priority = "high"
points = 3
parent = "01M6W7R0EPXRHEMNEAB9QWVY57"
reporter = "lognd"
created = "2026-11-08T00:08:19Z"
updated = "2026-11-08T01:17:13Z"
idempotency_key = "sadi-u4"
labels = ["ws:unc", "uncertainty", "model:sonnet", "creates:python/sadi/uncertainty/budget.py", "creates:python/tests/uncertainty/test_budget.py", "creates:docs/uncertainty/budget.md"]
scope = ["python/sadi/uncertainty/budget.py", "python/tests/uncertainty/test_budget.py", "docs/uncertainty/budget.md", "python/sadi/uncertainty/uncertain.py", "docs/uncertainty/uncertain.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R1RD3P97HFFDZ2NVD83Y"

[[acceptance]]
text = "`.budget(...)` returns per-input rows: value, u, sensitivity coefficient, contribution to u^2 (with covariance cross terms attributed and shown), percent of total, ranked; serialisable payload for the UI dominant-input panel"
bound = true

[[acceptance]]
text = "Budget sums to total variance exactly (property test), including correlated inputs"
bound = true
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). Python: typani Result[T, E] for every fallible operation (exceptions only for programmer bugs), pydantic models, run python -m typani.lint on new code.
