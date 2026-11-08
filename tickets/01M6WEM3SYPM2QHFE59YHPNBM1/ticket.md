+++
id = "01M6WEM3SYPM2QHFE59YHPNBM1"
title = "Wire data-root lock (store.lock.acquire) into session open and launcher startup"
type = "task"
category = "done"
outcome = "done"
priority = "high"
points = 2
parent = "01M6W7R04QJTECCTSV9EY2JADK"
reporter = "lognd"
created = "2026-11-08T02:08:29Z"
updated = "2026-11-08T02:14:21Z"
idempotency_key = "sadi-lock-wiring"
scope = ["python/sadi/store/session.py", "python/tests/store/test_session.py", "docs/store/lock.md"]

[[acceptance]]
text = "Opening or creating a session takes the data-root lock; a second process gets LockHeld with the holder pid and touches no data"
bound = true

[[acceptance]]
text = "LockStale surfaces to the caller with the recover_stale choice left to the user; docs/store/lock.md lists the callers"
bound = true
+++
