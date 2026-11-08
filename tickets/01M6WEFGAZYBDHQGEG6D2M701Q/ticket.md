+++
id = "01M6WEFGAZYBDHQGEG6D2M701Q"
title = "sadi store CLI: list, verify, recover and export sessions"
type = "task"
category = "done"
outcome = "done"
priority = "medium"
points = 5
parent = "01M6W7R04QJTECCTSV9EY2JADK"
reporter = "lognd"
created = "2026-11-08T02:05:58Z"
updated = "2026-11-08T02:10:52Z"
idempotency_key = "sadi-store-cli"
labels = ["creates:python/sadi/cli/store.py", "creates:python/tests/cli/test_store_cli.py", "creates:docs/store/cli.md"]
scope = ["python/sadi/cli/store.py", "python/tests/cli/test_store_cli.py", "docs/store/cli.md", "python/pyproject.toml", "python/sadi/cli/__init__.py", "docs/store/session.md"]

[[acceptance]]
text = "sadi store list/verify/recover/export subcommands operate read-only unless recover or export is requested; nothing is ever overwritten"
bound = true

[[acceptance]]
text = "verify reports WAL checksum status per segment with plain-language output and exit codes"
bound = true

[[acceptance]]
text = "export writes through write_csv_exclusive and refuses an existing target"
bound = true
+++
