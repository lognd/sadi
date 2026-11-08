+++
id = "01M6W88GQE0FH7PRJ64E1ANWQA"
title = "logging_setup binds stdout at first get_logger; breaks test_get_logger_routes_levels in full pytest run"
type = "bug"
category = "done"
outcome = "wont-fix"
priority = "medium"
reporter = "lognd"
created = "2026-11-08T00:17:17Z"
updated = "2026-11-08T00:19:43Z"
scope = ["python/sadi/logging_setup.py", "python/tests/test_scaffold.py"]
+++

found while working ~FY28A3R: any sadi module calling get_logger at import during collection binds handlers to collection-time stdout, so capsys in tests/test_scaffold.py::test_get_logger_routes_levels sees empty stdout in a full run. Fix: resolve sys.stdout/sys.stderr lazily, or use caplog in the test.
