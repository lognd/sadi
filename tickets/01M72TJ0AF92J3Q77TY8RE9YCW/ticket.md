+++
id = "01M72TJ0AF92J3Q77TY8RE9YCW"
title = "Spill import: failed fragment verify is retried (new crashed copy) on every start"
type = "bug"
category = "in-progress"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-10T13:32:29Z"
updated = "2026-11-10T13:37:40Z"
scope = ["python/sadi/store/spill.py", "python/tests/store/test_spill.py", "docs/store/spill.md", "changelog.d/01M72TJ0AF92J3Q77TY8RE9YCW.fixed.md"]

[[acceptance]]
text = "A fragment whose verify fails is marked so later starts do not re-copy it; nothing deleted"
bound = true
+++
