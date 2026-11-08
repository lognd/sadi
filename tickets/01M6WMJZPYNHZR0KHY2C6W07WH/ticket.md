+++
id = "01M6WMJZPYNHZR0KHY2C6W07WH"
title = "Mount save-indicator router in app and register mark_failed"
type = "task"
category = "in-progress"
priority = "high"
points = 3
reporter = "lognd"
created = "2026-11-08T03:52:43Z"
updated = "2026-11-08T03:53:53Z"
labels = ["feature"]
scope = ["python/sadi/server/app.py", "python/tests/server/test_app.py"]
+++

make_save_indicator_router (python/sadi/api/save_indicator.py) is not mounted in sadi/server/app.py and SaveIndicator.mark_failed is not registered as WriterHandle.on_failure, so GET /api/save-indicator is unreachable. Wire both and test through the app.
