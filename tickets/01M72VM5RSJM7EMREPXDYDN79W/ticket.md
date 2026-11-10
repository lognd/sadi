+++
id = "01M72VM5RSJM7EMREPXDYDN79W"
title = "Capture retry must never save a point twice (freeze body+id, narrow digest)"
type = "bug"
category = "done"
outcome = "done"
priority = "high"
points = 3
reporter = "lognd"
created = "2026-11-10T13:51:09Z"
updated = "2026-11-10T13:56:30Z"
scope = ["python/sadi/server/service.py", "python/tests/server/test_capture_request_id.py", "web/src/screens/review/api.ts", "web/src/screens/run/RunScreen.tsx", "web/src/screens/run/capture.ts", "web/src/screens/run/*.test.ts*", "docs/web/run-screens.md", "web/src/screens/run/loadChange.ts"]

[[acceptance]]
text = "Retry with same request_id but different live volts/window returns 201 Already saved and one point; client freezes body with attemptId, clears id only on request_id_reused; digest covers only operator-chosen fields; specimen POST not duplicated on retry; Run screen shows hint text not raw JSON"
bound = true
+++

Audit7 H1, M4, L8. See scratchpad audit7.md and a7/retry_dup.py.
