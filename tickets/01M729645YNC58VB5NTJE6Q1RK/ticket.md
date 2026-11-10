+++
id = "01M729645YNC58VB5NTJE6Q1RK"
title = "audit4 M1: no Origin/Host check; cross-site requests can close session, undo, write files"
type = "bug"
category = "todo"
priority = "high"
points = 3
reporter = "lognd"
created = "2026-11-10T08:28:54Z"
updated = "2026-11-10T08:28:54Z"
labels = ["audit4"]
scope = ["python/sadi/server/app.py", "python/sadi/server/security.py", "python/tests/server/test_origin_guard.py"]

[[acceptance]]
text = "middleware rejects non-local Host and unsafe-method/WS requests with foreign Origin or Sec-Fetch-Site cross-site; tests for each reproduced request"
bound = false
+++
