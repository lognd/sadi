+++
id = "01M6WK6V5B6CH2T7GVSS2SQ33J"
title = "Crash harness: drop rotated-WAL replay-equivalence skip now that 6H5B4R2 landed (fixes TODO002)"
type = "bug"
category = "in-progress"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-08T03:28:37Z"
updated = "2026-11-08T03:30:09Z"
scope = ["python/tests/crash/harness.py", "python/tests/crash/test_crash.py", "docs/store/crash-testing.md"]

[[acceptance]]
text = "Crash harness runs replay-equivalence on rotated WALs with no skip and no frob:todo"
bound = true
+++
