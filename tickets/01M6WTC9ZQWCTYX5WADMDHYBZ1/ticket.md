+++
id = "01M6WTC9ZQWCTYX5WADMDHYBZ1"
title = "REST: inventory CRUD and group weighing endpoints"
type = "task"
category = "in-progress"
priority = "medium"
points = 3
parent = "01M6W7R09P668G2VDDAWEDCSRM"
reporter = "lognd"
created = "2026-11-08T05:33:56Z"
updated = "2026-11-08T05:41:43Z"
labels = ["creates:python/sadi/server/routes/inventory.py", "creates:python/tests/server/test_inventory_routes.py", "creates:docs/server/inventory.md"]
scope = ["python/sadi/server/routes/inventory.py", "python/sadi/server/service.py", "python/tests/server/test_inventory_routes.py", "docs/server/inventory.md", "docs/index.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R3XY1B0BF689RX3H80G2"

[[acceptance]]
text = "REST: inventory CRUD and group weighing endpoints"
bound = true

[[acceptance]]
text = "Inventory events are durable NOTE records via SessionService; no deletes (edits are later events); provider-neutral port, 501 problem+json when no provider is installed"
bound = true

[[acceptance]]
text = "Tested with TestClient against the real WAL using a stub provider; docs/server/inventory.md written"
bound = true
+++

found while working ~X3H80G2 (split out of its original acceptance). Thin handlers over the weight inventory API.
