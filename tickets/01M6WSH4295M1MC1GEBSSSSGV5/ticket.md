+++
id = "01M6WSH4295M1MC1GEBSSSSGV5"
title = "Core Phase lacks tare/results/export phases"
type = "task"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-08T05:19:05Z"
updated = "2026-11-08T06:39:21Z"
scope = ["python/sadi/core/**", "python/sadi/labs/lctt/lab.py", "python/tests/labs/lctt/test_lab.py", "python/tests/core/test_models.py", "docs/lctt/lab-module.md", "docs/core/models.md", "web/src/api/openapi.json", "web/src/api/schema.ts"]
+++

found while working ~XMK16Q2: Tare is bound to the calibration phase and the wizard counts points by phase.value.
