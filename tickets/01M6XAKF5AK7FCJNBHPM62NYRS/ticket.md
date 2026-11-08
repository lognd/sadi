+++
id = "01M6XAKF5AK7FCJNBHPM62NYRS"
title = "Run phase: give the live run a real phase owner instead of inferring it for WS guidance"
type = "task"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-08T10:17:28Z"
updated = "2026-11-08T10:22:44Z"

[[acceptance]]
text = "The live run's phase is owned by SessionService, advanced only through validated forward transitions recorded as append-only WAL markers; WS guidance reads it and infers only for sessions without a recorded phase"
bound = true
+++
