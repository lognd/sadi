+++
id = "01M6W895B9GC8SF1RGMCM9EQSK"
title = "logging_setup binds sys.stdout at first get_logger call, breaking capsys tests"
type = "bug"
category = "done"
outcome = "done"
priority = "medium"
points = 1
reporter = "lognd"
created = "2026-11-08T00:17:39Z"
updated = "2026-11-08T00:20:42Z"
scope = ["python/sadi/logging_setup.py", "python/tests/test_scaffold.py", "docs/python-layout.md"]

[[acceptance]]
text = "Given other modules imported first, when get_logger routes INFO and WARNING under capsys, then INFO is on stdout and WARNING on stderr"
bound = true
+++

found while working ~SP19B1H: importing a module that calls get_logger at collection time attaches handlers to the then-current sys.stdout/stderr, so tests/test_scaffold.py::test_get_logger_routes_levels fails afterwards. Fix: resolve sys.stdout/sys.stderr per emit; then uncertainty modules can switch back to get_logger.
