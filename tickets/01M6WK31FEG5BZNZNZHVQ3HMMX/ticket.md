+++
id = "01M6WK31FEG5BZNZNZHVQ3HMMX"
title = "Launcher startup must acquire data-root lock and surface RootLockFailed"
type = "bug"
category = "todo"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-08T03:26:32Z"
updated = "2026-11-08T03:47:21Z"
scope = ["python/sadi/server/**"]
+++

found while working ~RMF702S: no launcher startup file exists yet that acquires the data-root lock; split from RMF702S
