+++
id = "01M6Z5DBWJ3K775HM54JKWYXSJ"
title = "Fix 12 ty errors in tests (FakeDwf arg types, Ok type args, skip_reason/status attrs) and ruff I001/other in tests/bench"
type = "task"
category = "in-progress"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-09T03:25:14Z"
updated = "2026-11-09T03:28:38Z"
idempotency_key = "gap-ty-tests-12"
scope = ["python/sadi/bench/lctt_source.py", "python/tests/bench/test_ad3_fake.py", "python/tests/bench/test_inject_capture_wait.py", "python/tests/doctor/test_ad3_checks.py", "changelog.d/*JKWYXSJ*"]

[[acceptance]]
text = "ty check sadi tests and ruff check . are clean"
bound = false
+++
