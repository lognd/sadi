+++
id = "01M6WBZ7QYZPJDF6XR283MEEZ0"
title = "JobManager: inject clock and executor instead of patching time/_spawn"
type = "task"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-08T01:22:08Z"
updated = "2026-11-08T03:03:57Z"
scope = ["python/sadi/jobs/*.py", "python/tests/jobs/*.py"]

[[acceptance]]
text = "JobManager accepts a clock and an executor/spawn factory; defaults unchanged"
bound = true

[[acceptance]]
text = "testing.py uses the seams, no module patching; all python/tests/jobs pass"
bound = false
+++

Follow-up from ~VAX9DG6: python/sadi/jobs/testing.py swaps the manager's time module and overrides _spawn. Add constructor-injected Clock and executor seams to JobManager so the harness stops patching globals (the time swap is process-global while a harness is open).
