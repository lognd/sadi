+++
id = "01M6WJHW2KET2M1730MZVJ1X4E"
title = "doctor: parallel execution and per-check/run timeouts"
type = "bug"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-08T03:17:10Z"
updated = "2026-11-08T04:32:42Z"
scope = ["python/sadi/doctor/**", "python/tests/doctor/**"]

[[acceptance]]
text = "Checks run in a thread pool but never before their in-selection depends_on prerequisites finish"
bound = true

[[acceptance]]
text = "Independent checks overlap and concurrency is bounded by the worker limit"
bound = true

[[acceptance]]
text = "A check exceeding its per-check timeout is reported skip/timeout (unverified) with a remedy and never hangs the run"
bound = true

[[acceptance]]
text = "The whole-run budget aborts running and unstarted checks as skip/timeout"
bound = false

[[acceptance]]
text = "Result order is the catalog order regardless of completion order, deterministic across runs"
bound = false

[[acceptance]]
text = "A crashing worker and a dependency cycle are handled (reported / raised), not lost or hung"
bound = false
+++

found while working ~V3H5CGF: runner is sequential, no budget
