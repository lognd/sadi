+++
id = "01M6W7RAFMFB5NMWGZY0VYJVFZ"
title = "`sadi` launcher: serve UI + API, pick port, open browser, flags"
type = "task"
category = "in-progress"
priority = "high"
points = 3
parent = "01M6W7R09P668G2VDDAWEDCSRM"
reporter = "lognd"
created = "2026-11-08T00:08:27Z"
updated = "2026-11-08T05:44:09Z"
idempotency_key = "sadi-l1"
labels = ["ws:srv", "model:sonnet", "creates:python/sadi/cli.py", "creates:python/sadi/__main__.py", "creates:python/tests/test_cli.py", "creates:docs/launcher.md"]
scope = ["python/sadi/cli.py", "python/sadi/__main__.py", "python/tests/test_cli.py", "docs/launcher.md", "python/sadi/launcher.py", "docs/server/launcher.md", "python/tests/test_launcher.py", "python/tests/cli/test_launcher.py"]

[[links]]
kind = "blocked-by"
target = "01M6W7R3XY1B0BF689RX3H80G2"

[[links]]
kind = "blocked-by"
target = "01M6W7R3ZPY606D3MHG4QRM2GS"

[[acceptance]]
text = "`sadi` starts uvicorn on a free localhost port, serves the built UI from package data, opens the default browser, handles Ctrl+C cleanly (flushes WAL); flags --sim, --port, --data-dir, --no-browser, --selftest, --version"
bound = true

[[acceptance]]
text = "Binds to 127.0.0.1 only; data dir default per-OS (platformdirs) and printed"
bound = true

[[acceptance]]
text = "--selftest runs a short simulator acquisition and exits non-zero on failure (used by C2)"
bound = true
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). Python: typani Result[T, E] for every fallible operation (exceptions only for programmer bugs), pydantic models, run python -m typani.lint on new code.
