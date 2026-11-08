+++
id = "01M6WFZF9FD9QNXP62MCETRNEA"
title = "Server API: plugins list endpoint and response models"
type = "task"
category = "todo"
priority = "medium"
points = 3
parent = "01M6WFY7CGXVKS192DN0WXNCH9"
reporter = "lognd"
created = "2026-11-08T02:32:10Z"
updated = "2026-11-08T02:32:10Z"
labels = ["plugins", "creates:python/sadi/plugins/api.py", "creates:python/sadi/server/routes_plugins.py", "creates:python/tests/plugins/test_api.py", "creates:python/tests/server/test_routes_plugins.py"]
scope = ["python/sadi/plugins/api.py", "python/sadi/server/routes_plugins.py", "python/tests/plugins/test_api.py", "python/tests/server/test_routes_plugins.py"]

[[links]]
kind = "blocked-by"
target = "01M6W7R09P668G2VDDAWEDCSRM"

[[links]]
kind = "blocked-by"
target = "01M6WFYN8C6YH5D79CPEKSP69P"

[[acceptance]]
text = "Endpoint JSON lists lctt enabled"
bound = false

[[acceptance]]
text = "Failed plugin appears with error text, endpoint still returns 200"
bound = false

[[acceptance]]
text = "Schema exported from pydantic model"
bound = false
+++

PluginStatus pydantic model (id, version, source, state, errors, findings) and list_plugin_status(registry) in plugins/api.py (framework-independent, unit tested). GET /api/plugins route in routes_plugins.py returns the list so the frontend can show it; also GET /api/plugins/{id}. NOTE: the server package does not exist yet (epic ~WEDCSRM); if the app factory is not present when this is picked up, land api.py plus a router object and record the mount as a follow-up ticket. Read-only: no enable/disable over HTTP.
