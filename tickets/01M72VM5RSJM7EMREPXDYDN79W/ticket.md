+++
id = "01M72VM5RSJM7EMREPXDYDN79W"
title = "Capture retry must never save a point twice (freeze body+id, narrow digest)"
type = "bug"
category = "in-progress"
priority = "high"
points = 3
reporter = "lognd"
created = "2026-11-10T13:51:09Z"
updated = "2026-11-10T13:51:17Z"
scope = ["python/sadi/server/service.py", "python/tests/server/test_capture_request_id.py", "web/src/screens/run/**", "web/src/screens/review/api.ts"]

[[acceptance]]
text = "Retry with same request_id but different live volts/window returns 201 Already saved and one point; client freezes body with attemptId, clears id only on request_id_reused; digest covers only operator-chosen fields; specimen POST not duplicated on retry; Run screen shows hint text not raw JSON"
bound = false
+++

Audit7 H1, M4, L8. See scratchpad audit7.md and a7/retry_dup.py.
