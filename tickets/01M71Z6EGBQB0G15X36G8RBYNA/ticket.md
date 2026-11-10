+++
id = "01M71Z6EGBQB0G15X36G8RBYNA"
title = "Audit1 #8 #43: synthetic driver verifies server results, fault path, quiet logging"
type = "bug"
category = "in-progress"
priority = "high"
points = 5
reporter = "lognd"
created = "2026-11-10T05:34:19Z"
updated = "2026-11-10T05:51:47Z"
scope = ["python/sadi/synthetic/**", "python/tests/synthetic/**"]

[[acceptance]]
text = "Driver checks /api/results from the server, fault scenarios pass, early return fixed, driver stdout logging quiet; tests added"
bound = false
+++
