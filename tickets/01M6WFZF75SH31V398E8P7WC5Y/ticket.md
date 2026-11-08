+++
id = "01M6WFZF75SH31V398E8P7WC5Y"
title = "CLI: sadi plugins list/info/enable/disable"
type = "task"
category = "in-progress"
priority = "medium"
points = 3
parent = "01M6WFY7CGXVKS192DN0WXNCH9"
reporter = "lognd"
created = "2026-11-08T02:32:10Z"
updated = "2026-11-08T02:56:57Z"
labels = ["plugins", "creates:python/sadi/cli/plugins.py", "creates:python/sadi/plugins/state.py", "creates:python/tests/cli/test_plugins_cli.py", "creates:python/tests/plugins/test_state.py"]
scope = ["python/sadi/cli/__init__.py", "python/sadi/cli/plugins.py", "python/sadi/plugins/state.py", "python/tests/cli/test_plugins_cli.py", "python/tests/plugins/test_state.py"]

[[links]]
kind = "blocked-by"
target = "01M6WFYN8C6YH5D79CPEKSP69P"

[[links]]
kind = "blocked-by"
target = "01M6WFZ1R6ATYWRVW3315G6CCX"

[[acceptance]]
text = "list shows lctt as builtin/enabled"
bound = true

[[acceptance]]
text = "disable then list shows disabled; enable restores"
bound = false

[[acceptance]]
text = "Unknown id returns clear error, no traceback"
bound = false
+++

Subcommands: list (table + --json), info <id> (manifest, source, state, errors, doctor findings when ticket for doctor is done), enable <id>, disable <id>. Enabled/disabled set persisted by plugins/state.py as a small atomic JSON file in the user config dir from PluginSettings (never in session dirs; use store/durable atomic replace via core-safe helper only if exposed, else stdlib tmp+replace). Errors are Result values rendered with exit codes: unknown id exit 2. Disabling takes effect on next start; say so in output.
