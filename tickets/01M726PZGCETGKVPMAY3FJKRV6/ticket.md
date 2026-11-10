+++
id = "01M726PZGCETGKVPMAY3FJKRV6"
title = "H1: export must not finish acquisition (GET export mid-run kills recording)"
type = "bug"
category = "in-progress"
priority = "high"
points = 3
reporter = "lognd"
created = "2026-11-10T07:45:41Z"
updated = "2026-11-10T07:50:36Z"
labels = ["creates:python/tests/server/test_export_no_finish.py"]
scope = ["python/sadi/server/routes/export.py", "python/sadi/server/live.py", "python/tests/server/test_export_no_finish.py", "docs/server/results.md", "docs/server/app.md", "python/tests/server/test_finish_wiring.py"]

[[acceptance]]
text = "GET /api/export/{fmt} (success or failure) never stops acquisition; a load change after a mid-run export still succeeds; finish happens only via POST /api/results/finish or close; capture gate refuses when stop_reason is finished/low_disk/idle/no_device; test covers both; raw data stays durable. DATA SAFETY: no data may be lost"
bound = true
+++
