+++
id = "01M6WVADCSP63DBMYH3RNCXWTM"
title = "Promote _captured/_points_for helpers from routes/results.py to a shared public module"
type = "chore"
category = "in-progress"
priority = "low"
points = 1
reporter = "lognd"
created = "2026-11-08T05:50:23Z"
updated = "2026-11-08T05:59:37Z"
labels = ["refactor"]
scope = ["python/sadi/server/session_points.py", "python/sadi/server/routes/results.py", "python/sadi/server/routes/export.py", "python/tests/server/test_session_points.py"]
+++

routes/export.py imports private helpers from routes/results.py; extract to a shared public module.
