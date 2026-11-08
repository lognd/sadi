+++
id = "01M6WTZVX9DFPHBKVJ1NXB07G0"
title = "launcher: --sim must make the server use the simulator (SADI_SIM is not read)"
type = "task"
category = "in-progress"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-08T05:44:37Z"
updated = "2026-11-08T05:51:39Z"
labels = ["ws:srv", "creates:python/sadi/__main__.py"]
scope = ["python/sadi/launcher.py", "python/sadi/__main__.py", "python/tests/cli/test_launcher.py", "python/tests/server/test_app.py", "docs/server/launcher.md"]

[[acceptance]]
text = "The sim flag or SADI_SIM makes the launcher pass a simulator device in AppSettings so /api/device/status reports simulated"
bound = false
+++

found in ~0VYJVFZ. launcher exports SADI_SIM=1 but nothing in server/app reads it. Also add python/sadi/__main__.py for python -m sadi.
