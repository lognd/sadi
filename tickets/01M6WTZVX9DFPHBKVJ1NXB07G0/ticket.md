+++
id = "01M6WTZVX9DFPHBKVJ1NXB07G0"
title = "launcher: --sim must make the server use the simulator (SADI_SIM is not read)"
type = "task"
category = "todo"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-08T05:44:37Z"
updated = "2026-11-08T05:44:37Z"
labels = ["ws:srv"]
+++

found in ~0VYJVFZ. launcher exports SADI_SIM=1 but nothing in server/app reads it. Also add python/sadi/__main__.py for python -m sadi.
