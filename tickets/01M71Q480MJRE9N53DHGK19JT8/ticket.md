+++
id = "01M71Q480MJRE9N53DHGK19JT8"
title = "JobManager reports DONE for a superseded job whose Done event races the kill (flaky on macOS)"
type = "bug"
category = "in-progress"
priority = "high"
points = 1
reporter = "lognd"
created = "2026-11-10T03:13:18Z"
updated = "2026-11-10T03:13:43Z"
scope = ["python/sadi/jobs/manager.py", "python/tests/jobs/test_manager.py", "changelog.d/*", "frob.lock"]

[[acceptance]]
text = "A job superseded or cancelled before its Done event is processed finishes SUPERSEDED/CANCELLED, never DONE"
bound = true
+++

CI run 42747216282 python (macos-latest): test_supersede_running_job_discards_old_result got DONE, discarded=True. _on_done always finishes with JobState.DONE even when job.outcome is already set.
