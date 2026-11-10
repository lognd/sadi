+++
id = "01M72X7S8DA8X3Q95HRYNKT2ED"
title = "Weight-subset planner: choose which of the 8 inventory weights to hang, in order, with GP gain and saturation limits"
type = "story"
category = "todo"
priority = "high"
points = 5
reporter = "lognd"
created = "2026-11-10T14:19:20Z"
updated = "2026-11-10T14:19:20Z"
labels = ["creates:python/sadi/design/plan.py", "creates:python/tests/design/test_plan.py", "creates:docs/design/weight-plan.md"]
scope = ["python/sadi/design/plan.py", "python/sadi/design/models.py", "python/tests/design/test_plan.py", "docs/design/weight-plan.md"]

[[acceptance]]
text = "Given an inventory of masses (duplicates allowed, each with a standard uncertainty), a specimen geometry and a calibration slope, plan() returns an ordered list of hangs (each a multiset of inventory weight ids with total mass and its propagated uncertainty) chosen by GP/expected-gain over the achievable subset sums; every hang keeps predicted |V| and tension below saturation and wire capacity; duplicates are distinct ids; deterministic; Result[T,E] errors; tests cover duplicates, saturation clipping, fewer usable weights than 8"
bound = false
+++

User request: the lab hands out about 8 weights of varying sizes (sometimes duplicates). Pick the subset to use (weight #1, #2, #3 ...) with uncertainty, considering saturation (LVDT |V| threshold saturation.py, wire capacity) and the GP selector (docs/design/gp-selector.md). Achievable loads are the 2^n subset sums (n<=8 so exhaustive); dedupe equal multisets but keep ids. Reuse selector.py gain; no duplication. Advisory only, never writes data.
