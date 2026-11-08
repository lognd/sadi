+++
id = "01M6WMGMM1BP37GS27VRRX9AYP"
title = "Add sadi launcher CLI entry that starts server and serves web"
type = "task"
category = "in-progress"
priority = "high"
points = 3
reporter = "lognd"
created = "2026-11-08T03:51:27Z"
updated = "2026-11-08T03:55:44Z"
labels = ["feature", "creates:python/sadi/launcher.py", "creates:python/tests/cli/test_launcher.py", "creates:docs/server/launcher.md"]
scope = ["python/sadi/launcher.py", "python/pyproject.toml", "python/tests/cli/test_launcher.py", "docs/server/launcher.md"]

[[acceptance]]
text = "sadi serve runs doctor preflight, takes the data-root lock (refused lock exits non-zero), serves web/dist, defaults host 127.0.0.1"
bound = false
+++

No sadi launcher or server CLI entry exists. Add a console script that runs doctor preflight, takes the data-root lock via create_app, starts uvicorn and serves the built web assets.
