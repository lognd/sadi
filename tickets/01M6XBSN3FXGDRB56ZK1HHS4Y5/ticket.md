+++
id = "01M6XBSN3FXGDRB56ZK1HHS4Y5"
title = "COV001 in tools mains plus ruff errors in sadi-py tests"
type = "chore"
category = "in-progress"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-08T10:38:19Z"
updated = "2026-11-08T10:39:20Z"
scope = ["crates/sadi-py/tests/test_acq.py", "crates/sadi-py/tests/test_sim.py", "python/sadi/server/service.py", "python/tests/packaging/test_build_ui.py"]

[[acceptance]]
text = "Clear COV001 for packaging/build_ui.py main and tools/check_typani_collisions.py main; fix 3 ruff errors in crates/sadi-py/tests and E501 at python/sadi/server/service.py:393"
bound = false
+++
