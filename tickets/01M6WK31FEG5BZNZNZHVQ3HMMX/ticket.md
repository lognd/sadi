+++
id = "01M6WK31FEG5BZNZNZHVQ3HMMX"
title = "Launcher startup must acquire data-root lock and surface RootLockFailed"
type = "bug"
category = "in-progress"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-08T03:26:32Z"
updated = "2026-11-08T03:48:46Z"
scope = ["python/sadi/server/**", "docs/server/app.md", "python/tests/server/test_app.py"]

[[acceptance]]
text = "App startup holds the data-root lock for its lifetime and releases it on shutdown"
bound = true

[[acceptance]]
text = "A held or stale lock fails startup with a typed RootLockFailed and is never stolen"
bound = true

[[acceptance]]
text = "A degraded start exposes the lock failure at GET /api/root-lock"
bound = true
+++

found while working ~RMF702S: no launcher startup file exists yet that acquires the data-root lock; split from RMF702S
