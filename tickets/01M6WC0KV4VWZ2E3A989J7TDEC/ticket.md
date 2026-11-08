+++
id = "01M6WC0KV4VWZ2E3A989J7TDEC"
title = "Route specimen ids and titles through sanitize_name in the session store"
type = "task"
category = "in-progress"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-08T01:22:53Z"
updated = "2026-11-08T03:03:50Z"
scope = ["python/sadi/store/session.py", "python/tests/store/test_session.py"]

[[acceptance]]
text = "User-derived names used in paths go through sanitize_name/unique_name"
bound = true

[[acceptance]]
text = "Tests show reserved Windows names and forbidden characters cannot reach the filesystem"
bound = true
+++

Follow-up from ~T5XVYE8: python/sadi/store/names.py exists but session.py does not call it for user-derived specimen ids or titles.
