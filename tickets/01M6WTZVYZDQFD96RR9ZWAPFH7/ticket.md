+++
id = "01M6WTZVYZDQFD96RR9ZWAPFH7"
title = "pyproject: declare platformdirs dependency"
type = "task"
category = "in-progress"
priority = "low"
points = 1
reporter = "lognd"
created = "2026-11-08T05:44:37Z"
updated = "2026-11-08T05:45:16Z"
labels = ["ws:srv"]
scope = ["python/pyproject.toml", "python/uv.lock"]

[[acceptance]]
text = "platformdirs is declared in python/pyproject.toml"
bound = true
+++

found in ~0VYJVFZ: launcher.default_data_dir uses platformdirs, only transitively installed.
