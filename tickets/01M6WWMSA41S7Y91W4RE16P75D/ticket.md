+++
id = "01M6WWMSA41S7Y91W4RE16P75D"
title = "Add TYP004 hints to problem+json errors in routes/inventory.py and routes/export.py"
type = "task"
category = "in-progress"
priority = "medium"
points = 1
reporter = "lognd"
created = "2026-11-08T06:13:31Z"
updated = "2026-11-08T06:17:28Z"
scope = ["python/sadi/server/routes/inventory.py", "python/sadi/server/routes/export.py"]

[[acceptance]]
text = "inventory.py and export.py propagate errors via @propagate/unwrap with no TYP004 findings and unchanged problem+json behaviour"
bound = false
+++
