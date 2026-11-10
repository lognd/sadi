+++
id = "01M72X7ZB936PEBXHRGX06FSAD"
title = "Weight plan route and UI: enter the 8 weights, show ordered hangs with uncertainty on Setup and Run"
type = "story"
category = "in-progress"
priority = "high"
points = 5
reporter = "lognd"
created = "2026-11-10T14:19:26Z"
updated = "2026-11-10T14:40:12Z"
labels = ["creates:python/sadi/server/routes/weight_plan.py", "creates:python/tests/server/test_weight_plan_route.py", "creates:web/src/screens/setup/WeightPlanPanel.tsx", "creates:web/src/screens/setup/WeightPlanPanel.test.tsx"]
scope = ["python/sadi/server/routes/weight_plan.py", "python/tests/server/test_weight_plan_route.py", "web/src/screens/setup/WeightPlanPanel.tsx", "web/src/screens/setup/WeightPlanPanel.test.tsx", "python/sadi/server/app.py", "web/src/App.tsx", "web/src/api/openapi.json", "web/src/api/schema.ts", "docs/design/weight-plan.md"]

[[links]]
kind = "blocked-by"
target = "01M72X7S8DA8X3Q95HRYNKT2ED"

[[links]]
kind = "blocked-by"
target = "01M72X7SDBW19CXXYQA63ECN6C"

[[acceptance]]
text = "GET/POST route returns the plan from the entered inventory; Setup has a panel to enter weights (mass, unit, duplicates, uncertainty) persisted via the existing inventory events (append only); the panel shows Hang #1, #2, ... with total mass, predicted volts, and plus/minus uncertainty with plain wording; Run screen shows the next planned hang and re-plans from actual points; OpenAPI and schema.ts regenerated; docs and changelog"
bound = false
+++

Front end and API for the weight-subset planner and error propagation tickets. Consume the InventoryProvider port in routes/inventory.py; never write data except the append-only inventory events.
