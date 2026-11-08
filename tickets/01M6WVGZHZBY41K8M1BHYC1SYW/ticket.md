+++
id = "01M6WVGZHZBY41K8M1BHYC1SYW"
title = "Results API lacks provenance (which settle value fed E); export screen shows stand-in notes"
type = "task"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-08T05:53:58Z"
updated = "2026-11-08T05:58:37Z"
labels = ["server"]
scope = ["python/sadi/server/routes/results.py", "python/tests/server/test_results_routes.py", "docs/server/results.md", "docs/web/export-screen.md"]

[[acceptance]]
text = "GET /api/results includes a provenance list on the wire"
bound = true

[[acceptance]]
text = "Each quantity provenance names point ids, sample span and algorithm"
bound = false
+++

GET /api/results has no provenance field. Add per-quantity provenance (settle window, point ids, algorithm) and show it in web/src/screens/export.
