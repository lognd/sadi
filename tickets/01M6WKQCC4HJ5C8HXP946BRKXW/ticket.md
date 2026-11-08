+++
id = "01M6WKQCC4HJ5C8HXP946BRKXW"
title = "FastAPI app factory: mount doctor and plugins routers"
type = "task"
category = "in-progress"
priority = "high"
points = 3
reporter = "lognd"
created = "2026-11-08T03:37:39Z"
updated = "2026-11-08T03:40:01Z"
labels = ["creates:python/sadi/server/app.py", "creates:python/tests/server/test_app.py", "creates:docs/server/app.md"]
scope = ["python/sadi/server/app.py", "python/tests/server/test_app.py", "docs/server/app.md", "python/tests/test_docs_index.py", "docs/web/doctor-ui.md"]

[[acceptance]]
text = "create_app mounts the doctor and plugins routers"
bound = true

[[acceptance]]
text = "Unknown routes return 404 and settings are injected per app"
bound = true
+++
