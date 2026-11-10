+++
id = "01M71T683VDS38T2GYYW9SXT5B"
title = "Backend: expose firmware, sample rate, and active data root in a status endpoint"
type = "task"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-10T04:06:50Z"
updated = "2026-11-10T15:36:41Z"
labels = ["creates:python/tests/server/test_status_route.py", "creates:python/sadi/server/routes/status.py", "creates:docs/server/status.md"]
scope = ["python/sadi/server/routes/status.py", "python/tests/server/test_status_route.py", "docs/server/status.md", "python/sadi/server/app.py", "python/sadi/server/live.py", "web/src/components/instrument/DebugStrip.tsx", "web/src/components/instrument/useBackendFacts.ts", "web/src/components/instrument/instrument.test.tsx", "docs/server/api.md"]

[[acceptance]]
text = "GET /api/status returns firmware, sample_rate_hz and data_root (the active --data-root); tested"
bound = true
+++

found while working ~D7DHSW4: debug strip shows firmware as unavailable; sample rate and active data folder are only inferred (doctor reports the default root, not --data-root).
