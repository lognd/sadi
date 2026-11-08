+++
id = "01M6WH4Q5S0YYD0S8YW9T1EX41"
title = "lctt plugin: wire real per-phase analysis into LcttLab.recompute (currently a stub)"
type = "task"
category = "in-progress"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-08T02:52:30Z"
updated = "2026-11-08T06:59:44Z"
scope = ["python/sadi/core/models.py", "python/sadi/server/session_points.py", "python/sadi/labs/lctt/lab.py", "python/tests/**", "docs/core/models.md"]

[[acceptance]]
text = "CapturedPoint gains optional volts, volts_sd, load_kg (additive, defaults None so old WAL/session data still loads); capture paths populate them; LcttLab.recompute returns real stress/strain/modulus values from them"
bound = false
+++
