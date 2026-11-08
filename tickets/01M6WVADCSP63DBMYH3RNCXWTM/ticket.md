+++
id = "01M6WVADCSP63DBMYH3RNCXWTM"
title = "Promote _captured/_points_for helpers from routes/results.py to a shared public module"
type = "chore"
category = "in-progress"
priority = "low"
points = 1
reporter = "lognd"
created = "2026-11-08T05:50:23Z"
updated = "2026-11-08T06:01:39Z"
labels = ["refactor"]
scope = ["python/sadi/server/session_points.py", "python/sadi/server/routes/results.py", "python/sadi/server/routes/export.py", "python/tests/server/test_session_points.py", "changelog.d/01M6WVADCSP63DBMYH3RNCXWTM.changed.md"]

[[acceptance]]
text = "Helpers live in public sadi.server.session_points and routes/export no longer imports private names from routes/results"
bound = true

[[acceptance]]
text = "Behaviour unchanged: tests/server passes"
bound = true
+++

routes/export.py imports private helpers from routes/results.py; extract to a shared public module.
