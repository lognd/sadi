+++
id = "01M6WMQVSEMD3FGD21ZS7V3W3P"
title = "Backend: supply settle_band in creep payload"
type = "task"
category = "in-progress"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-08T03:55:23Z"
updated = "2026-11-08T03:57:50Z"
labels = ["feature"]
scope = ["python/sadi/labs/lctt/creep.py", "python/tests/labs/lctt/test_creep.py", "docs/lctt/creep.md"]
+++

buildCreepScene (web/src/plots/creep) expects settle_band (strain band for the settle threshold span); the creep analysis payload does not produce it today. Add to the creep analysis output and the API schema, with tests.
