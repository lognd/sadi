+++
id = "01M7305JYQ6AZA2Z92Y5QQ54BF"
title = "Planner picks which gauge heights to use (height inventory like weights) with per-height uncertainty"
type = "story"
category = "in-progress"
priority = "high"
points = 3
reporter = "lognd"
created = "2026-11-10T15:10:34Z"
updated = "2026-11-10T15:20:58Z"
labels = ["creates:python/tests/design/test_height_plan.py"]
scope = ["python/sadi/design/**", "python/tests/design/**", "docs/design/**"]

[[links]]
kind = "blocked-by"
target = "01M7301MDWNXK9Z0D8TBDBNP4G"

[[acceptance]]
text = "Planner accepts an inventory of available gauge heights (m) each with its own uncertainty, GUI table and CLI --heights h:u,..."
bound = false

[[acceptance]]
text = "Returns the ordered subset of heights to use for calibration, accounting for LVDT saturation and the GP selector, same as weights"
bound = false

[[acceptance]]
text = "Each chosen height reports its uncertainty and the propagated uncertainty in the calibration slope/intercept (weighted fit using per-height u)"
bound = false

[[acceptance]]
text = "Duplicates in the height inventory stay distinct ids; error when fewer than 2 distinct usable heights"
bound = false
+++

User: heights are just like the weights; need to know which heights to use and the uncertainty in them. Reuse selector.py; do not duplicate the weight logic.
