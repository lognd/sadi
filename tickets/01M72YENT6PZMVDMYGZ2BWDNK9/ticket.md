+++
id = "01M72YENT6PZMVDMYGZ2BWDNK9"
title = "Weight plan: persist inventory via append-only events and replan on Run screen"
type = "story"
category = "todo"
priority = "medium"
points = 5
reporter = "lognd"
created = "2026-11-10T14:40:35Z"
updated = "2026-11-10T14:40:35Z"
scope = ["python/sadi/server/routes/weight_plan.py", "web/src/screens/setup/**", "web/src/screens/run/**"]

[[links]]
kind = "blocked-by"
target = "01M72X7ZB936PEBXHRGX06FSAD"

[[acceptance]]
text = "Weights persist via inventory events."
bound = false

[[acceptance]]
text = "Run screen shows next planned hang and replans from captured points."
bound = false
+++
