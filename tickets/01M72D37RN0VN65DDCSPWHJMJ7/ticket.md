+++
id = "01M72D37RN0VN65DDCSPWHJMJ7"
title = "Run-step guidance wording, accept-key repeat guard, capture request_id idempotency, sim load-change phase (audit5 M5 L1 L7 MED11)"
type = "bug"
category = "todo"
priority = "high"
points = 8
reporter = "lognd"
created = "2026-11-10T09:37:14Z"
updated = "2026-11-10T09:37:52Z"
labels = ["creates:python/tests/server/test_capture_request_id.py", "creates:python/tests/server/test_live_load_change.py"]
scope = ["python/sadi/labs/lctt/gp_suggester.py", "python/sadi/labs/lctt/guidance.py", "python/sadi/labs/lctt/capture.py", "python/sadi/server/live.py", "python/sadi/server/schemas.py", "python/sadi/server/service.py", "python/sadi/server/session_points.py", "web/src/screens/run/**", "web/src/keys/**", "python/tests/server/test_routes_acquisition.py", "python/tests/server/test_service_snapshots.py", "python/tests/server/test_capture_request_id.py", "python/tests/server/test_live_load_change.py", "python/tests/labs/lctt/test_guidance.py", "python/tests/labs/lctt/test_gp_suggester.py", "python/tests/labs/lctt/test_capture.py", "python/tests/labs/lctt/test_capture_record.py", "python/tests/labs/lctt/test_settle_stream.py", "web/src/api/client.ts", "web/src/api/client.test.ts", "docs/lctt/guidance.md", "docs/lctt/capture.md"]

[[acceptance]]
text = "No guidance text contains 'total'; accept keys ignore repeat and block duplicate accept; capture replay with same request_id returns existing commit; sim tare/calibrate mark does not add load; openapi regenerated"
bound = false
+++

audit5 M5, L1, L7, MED 11 part of M6. Data-safety: no data loss, atomic, never overwritten.
