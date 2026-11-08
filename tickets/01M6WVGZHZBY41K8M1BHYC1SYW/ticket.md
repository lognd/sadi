+++
id = "01M6WVGZHZBY41K8M1BHYC1SYW"
title = "Results API lacks provenance (which settle value fed E); export screen shows stand-in notes"
type = "task"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-08T05:53:58Z"
updated = "2026-11-08T05:57:45Z"
labels = ["server"]
+++

GET /api/results has no provenance field. Add per-quantity provenance (settle window, point ids, algorithm) and show it in web/src/screens/export.
