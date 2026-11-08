+++
id = "01M6WYFEHRTTR9AY8BEMN9CQ6S"
title = "Expose ByteFaultPlan in sadi_py.sim bindings"
type = "bug"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-08T06:45:33Z"
updated = "2026-11-08T06:49:14Z"
scope = ["crates/**", "docs/**"]

[[acceptance]]
text = "Given a valid ByteFaultPlan, when sadi_py.sim.open is called with byte_faults, then the session stream is deterministically corrupted and invalid plans raise ScenarioFailure"
bound = true
+++

found while working ~WKK27QJ
