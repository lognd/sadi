+++
id = "01M71YY12XP2ZDM402A00A7RJW"
title = "Data safety: server never writes snapshots (snapshot.write_snapshot unused)"
type = "bug"
category = "in-progress"
priority = "high"
points = 5
reporter = "lognd"
created = "2026-11-10T05:29:43Z"
updated = "2026-11-10T06:01:35Z"
scope = ["python/sadi/store/**", "python/sadi/server/service.py", "docs/data-safety.md", "python/tests/server/test_service_snapshots.py"]

[[acceptance]]
text = "Server writes periodic atomic snapshots of live sessions via snapshot.write_snapshot; recoverable after SIGKILL; docs/data-safety.md updated"
bound = false
+++
