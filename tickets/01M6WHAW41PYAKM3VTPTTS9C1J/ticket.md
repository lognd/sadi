+++
id = "01M6WHAW41PYAKM3VTPTTS9C1J"
title = "Fix ruff errors in plugins/local.py"
type = "task"
category = "in-progress"
priority = "medium"
points = 1
reporter = "lognd"
created = "2026-11-08T02:55:52Z"
updated = "2026-11-08T02:56:44Z"
scope = ["python/sadi/plugins/local.py", "python/tests/plugins/test_local_source.py"]
+++

uv run ruff check . reports 3 errors (I001, E501, one more) in python/sadi/plugins/local.py. Fix with no behavior change.
