+++
id = "01M6WVJ5SYGQK3ESRH7AMECWPX"
title = "PointView lacks settled/forced_early flags for review screen"
type = "bug"
category = "in-progress"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-08T05:54:37Z"
updated = "2026-11-08T06:11:17Z"
labels = ["ws:server"]
scope = ["python/tests/server/test_routes.py", "web/src/api/openapi.json", "web/src/api/schema.ts", "web/src/screens/review/types.ts", "docs/server/results.md", "docs/web/review-screen.md", "python/sadi/server/schemas.py"]

[[acceptance]]
text = "GET /api/session/points returns settled and forced_early per point from the captured PointV1"
bound = true
+++

found while working ~FHNEDX8: PointView omits settled and forced_early from PointV1; review screen shows them only when present.
