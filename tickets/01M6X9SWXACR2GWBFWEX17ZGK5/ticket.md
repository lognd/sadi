+++
id = "01M6X9SWXACR2GWBFWEX17ZGK5"
title = "Flaky test_curve_notes_latency under periodic re-verify; check test_wal throughput flake"
type = "bug"
category = "done"
outcome = "done"
priority = "medium"
points = 1
reporter = "lognd"
created = "2026-11-08T10:03:30Z"
updated = "2026-11-08T10:10:35Z"
scope = ["python/tests/server/test_curve_notes_latency.py"]

[[acceptance]]
text = "test_curve_notes_latency is deterministic under the periodic re-verify (injected clock or relaxed trigger) and passes 10 consecutive runs"
bound = true
+++
