+++
id = "01M703DQRSCSJX53A7ETHQ67F3"
title = "ci: typani TYP007 in jobs/testing.py and macOS python test failures"
type = "bug"
category = "in-progress"
priority = "high"
points = 2
reporter = "lognd"
created = "2026-11-09T12:09:43Z"
updated = "2026-11-09T12:14:33Z"
scope = ["python/tests/conftest.py", "python/tests/server/test_spill_isolation.py", "python/tests/store/test_durable.py"]

[[acceptance]]
text = "typani lint clean; the 3 macOS tests pass logic-wise on Linux and path handling is symlink-safe"
bound = false
+++

CI run 42611895998. (1) python/sadi/jobs/testing.py:316 TYP007 'except Exception' inside Result-returning fn (typani lint fails on python macos+windows): name exceptions or use Result.catch. (2) macOS: tests/server/test_spill_isolation.py (2 tests) compare /private/var vs /var symlink paths (user_data_dir() vs tmp path; resolve both sides or fix the product path normalisation if it is a real inconsistency); tests/store/test_durable.py::test_fsync_file_error_is_result gets Ok(None) instead of Err on macOS (fsync of a bad fd semantics / F_FULLFSYNC: make the product return Err for a real failure, or fix test fixture). Logs: gh api repos/lognd/sadi/actions/jobs/129142243483/logs. Do not weaken data-safety.
