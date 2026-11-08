+++
id = "01M6X9CP3SGVZ93H22ARANVN2E"
title = "SessionReplayCache: periodically re-verify already-applied WAL bytes (export must never serve unverified data)"
type = "task"
category = "in-progress"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-08T09:56:17Z"
updated = "2026-11-08T10:02:48Z"
scope = ["python/sadi/server/curve_source.py", "python/sadi/server/routes/export.py"]

[[acceptance]]
text = "Export and live views detect corruption in already-applied WAL bytes"
bound = true
+++
