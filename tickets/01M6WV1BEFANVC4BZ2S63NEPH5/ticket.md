+++
id = "01M6WV1BEFANVC4BZ2S63NEPH5"
title = "lctt recompute is a stub; CapturedPoint time fields missing from PointView"
type = "bug"
category = "done"
outcome = "done"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-08T05:45:26Z"
updated = "2026-11-08T06:29:46Z"
scope = ["python/sadi/labs/**,python/sadi/server/**", "python/sadi/server/schemas.py", "python/sadi/server/session_points.py", "python/tests/server/test_session_points.py", "web/src/api/openapi.json", "web/src/api/schema.ts"]

[[acceptance]]
text = "PointView carries t_since_load_s and drift_rate; to_captured maps them and forced_early into CapturedPoint"
bound = true
+++

found while working ~J73KJ11: t_since_load and drift are zeroed in results._captured
