+++
id = "01M6WMGMM1BP37GS27VRRX9AYP"
title = "Add sadi launcher CLI entry that starts server and serves web"
type = "task"
category = "todo"
priority = "high"
points = 3
reporter = "lognd"
created = "2026-11-08T03:51:27Z"
updated = "2026-11-08T03:51:27Z"
labels = ["feature"]
+++

No sadi launcher or server CLI entry exists. Add a console script that runs doctor preflight, takes the data-root lock via create_app, starts uvicorn and serves the built web assets.
