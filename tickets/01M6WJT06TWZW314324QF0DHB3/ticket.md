+++
id = "01M6WJT06TWZW314324QF0DHB3"
title = "Writing indicator: show saving state within 250 ms"
type = "task"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-08T03:21:36Z"
updated = "2026-11-08T03:52:17Z"
scope = ["python/sadi/api/**", "python/tests/server/test_save_indicator.py", "docs/ux.md"]

[[acceptance]]
text = "Header save state reads Saving... whenever records are enqueued but not durable, visible to a 250 ms poll"
bound = true

[[acceptance]]
text = "Saved HH:MM:SS when all enqueued records are durable; NOT SAVED latches on writer failure"
bound = true
+++

found while working ~60ZNFTD
