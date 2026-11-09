+++
id = "01M6Z4M4YQDHZ97PC9A81E3CP7"
title = "frob test --base main: pytest collection errors in sadi-py tests"
type = "bug"
category = "done"
outcome = "wont-fix"
priority = "medium"
reporter = "lognd"
created = "2026-11-09T03:11:28Z"
updated = "2026-11-09T03:13:05Z"
scope = ["crates/sadi-py/**"]
+++

found while working ~FEV63Y8: frob test --base main fails with pytest exit 4 (collection errors in python/sadi_py/tests/test_smoke.py, tests/test_acq.py, tests/test_sim.py); the same run against the branch base 6c4b35a2 passes. Those files live at crates/sadi-py/ on main.
