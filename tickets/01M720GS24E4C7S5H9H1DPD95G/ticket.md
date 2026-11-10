+++
id = "01M720GS24E4C7S5H9H1DPD95G"
title = "Server /api/results omits yield_stress for the lctt lab (analyze stub)"
type = "bug"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-10T05:57:26Z"
updated = "2026-11-10T06:05:12Z"
scope = ["python/sadi/server/**,python/sadi/labs/lctt/**", "docs/server/results.md", "python/tests/labs/lctt/test_lab_analyze_e2e.py", "python/tests/synthetic/test_results_pending.py"]

[[acceptance]]
text = "GET /api/results carries yield_stress or a pending/notes reason; found while working ~G8RBYNA"
bound = false
+++
