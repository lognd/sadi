+++
id = "01M6WV1BBQYWGMK7W6KDD8P2N2"
title = "Lab budget hook so /api/results/budgets is non-empty"
type = "bug"
category = "in-progress"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-08T05:45:26Z"
updated = "2026-11-08T06:04:02Z"
scope = ["python/sadi/server/**", "python/sadi/labs/**", "python/sadi/core/lab.py", "python/tests/**", "docs/server/results.md", "web/src/api/openapi.json"]

[[acceptance]]
text = "GET /api/results/budgets returns the lab budgets when no source is injected"
bound = true

[[acceptance]]
text = "A lab without the budgets hook yields an empty list"
bound = false
+++

found while working ~J73KJ11: budgets are an injectable BudgetSource; no lab supplies one yet
