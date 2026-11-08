+++
id = "01M6WEYV1HZCER8M2NVRMF702S"
title = "Surface RootLockFailed in sadi CLI recover and launcher startup"
type = "bug"
category = "in-progress"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-08T02:14:20Z"
updated = "2026-11-08T03:26:42Z"
scope = ["python/sadi/cli/store.py,python/tests/cli/test_store_cli.py", "python/sadi/cli/store.py", "python/tests/cli/test_store_cli.py", "docs/store/cli.md"]

[[acceptance]]
text = "sadi store recover names the cause of a data-root lock refusal (held, stale, io) and accepts --recover-stale to take over a stale lock"
bound = false
+++

found while working YHPNBM1: cmd_recover shows only a generic message for RootLockFailed; no launcher startup acquires the lock; recover_stale is not exposed to the user.
