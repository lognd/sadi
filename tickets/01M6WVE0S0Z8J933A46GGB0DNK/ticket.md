+++
id = "01M6WVE0S0Z8J933A46GGB0DNK"
title = "Verify --sim against a real built sadi_py simulator (launcher tests inject fake)"
type = "task"
category = "in-progress"
priority = "low"
points = 2
reporter = "lognd"
created = "2026-11-08T05:52:21Z"
updated = "2026-11-08T06:03:30Z"
labels = ["python"]
scope = ["python/tests/cli/test_launcher.py", "docs/server/launcher.md", "changelog.d"]

[[acceptance]]
text = "open_sim_device opens against a real built sadi_py and streams samples (test skipped when sadi_py is not importable)"
bound = true

[[acceptance]]
text = "docs/server/launcher.md records the verification status"
bound = false
+++

NXB07G0 tests inject a fake device; run open_sim_device against a built sadi_py once maturin develop is available.
