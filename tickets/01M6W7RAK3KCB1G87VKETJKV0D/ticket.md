+++
id = "01M6W7RAK3KCB1G87VKETJKV0D"
title = "Versioned results stream: instant analytic, progressive refinement, stale markers"
type = "task"
category = "in-progress"
priority = "high"
points = 5
parent = "01M6W7R0G9VM8M2C0QQNX209CZ"
reporter = "lognd"
created = "2026-11-08T00:08:27Z"
updated = "2026-11-08T05:57:12Z"
idempotency_key = "sadi-j4"
labels = ["ws:conc", "ws:srv", "model:sonnet", "creates:python/sadi/server/results_stream.py", "creates:python/tests/server/test_results_stream.py", "creates:docs/server/results-stream.md"]
scope = ["python/sadi/server/results_stream.py", "python/tests/server/test_results_stream.py", "docs/server/results-stream.md", "docs/server/websocket.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R3G88NFY3N76MPX6X3ZQ"

[[links]]
kind = "blocked-by"
target = "01M6W7R3J00J2HQ7XPW19WDD6Q"

[[links]]
kind = "blocked-by"
target = "01M6W7R3ZPY606D3MHG4QRM2GS"

[[acceptance]]
text = "Every result carries (data_version, result_version, state: analytic|refining|final|stale, progress); UI never receives a number without its version and marker"
bound = true

[[acceptance]]
text = "After each captured point the analytic result is pushed immediately (stale refinements are discarded), then MC/GP refinements stream until final"
bound = true

[[acceptance]]
text = "Reconnecting clients get the latest snapshot; protocol documented and versioned (protocol_version field)"
bound = true
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). Python: typani Result[T, E] for every fallible operation (exceptions only for programmer bugs), pydantic models, run python -m typani.lint on new code.
