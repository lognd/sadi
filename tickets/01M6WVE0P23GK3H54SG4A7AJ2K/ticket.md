+++
id = "01M6WVE0P23GK3H54SG4A7AJ2K"
title = "Python lint debt: ty error in test_loop_lag.py and ruff format/check findings"
type = "chore"
category = "done"
outcome = "done"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-08T05:52:21Z"
updated = "2026-11-08T05:54:43Z"
labels = ["python"]
scope = ["python/**"]

[[acceptance]]
text = "ty, ruff format and ruff check clean"
bound = true
+++

ty: tests/server/test_loop_lag.py:57 Err missing type args. ruff format --check reports 9 files; ruff check reports errors outside recent tickets. Fix all so python gates are clean.
