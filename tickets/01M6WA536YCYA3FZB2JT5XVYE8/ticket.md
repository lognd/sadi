+++
id = "01M6WA536YCYA3FZB2JT5XVYE8"
title = "Filename sanitiser for user-derived names (Windows reserved, forbidden chars, length)"
type = "task"
category = "done"
outcome = "done"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-08T00:50:23Z"
updated = "2026-11-08T01:22:31Z"
scope = ["python/sadi/store/names.py", "python/tests/store/test_names.py", "docs/store/names.md", "docs/README.md", "docs/portability.md"]

[[acceptance]]
text = "Output valid on Windows/Linux/macOS (reserved names, forbidden chars, length)"
bound = true

[[acceptance]]
text = "Idempotent and distinct inputs do not collide; unique_name never returns a taken name"
bound = true
+++
