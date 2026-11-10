+++
id = "01M72T4R1WNQRV303D0WJXW1MW"
title = "Capture request_id reused for a different point is silently dropped; make replay body-aware"
type = "bug"
category = "in-progress"
priority = "high"
points = 3
reporter = "lognd"
created = "2026-11-10T13:25:15Z"
updated = "2026-11-10T13:32:21Z"
labels = ["creates:none"]
scope = ["python/sadi/server/service.py", "python/tests/server/test_capture_request_id.py", "web/src/screens/run/RunScreen.tsx"]

[[acceptance]]
text = "Server stores digest per request_id and returns 409 on mismatch; lookup repeated under lock in _act; client resets attemptId on load change/field edit; replay message plain English; tests"
bound = true
+++

Audit6 M2,L1. Client keeps attemptId after load change; server _existing_capture ignores inputs; lookup and write under separate lock acquisitions.
