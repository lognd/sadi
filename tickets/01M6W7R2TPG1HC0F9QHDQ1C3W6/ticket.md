+++
id = "01M6W7R2TPG1HC0F9QHDQ1C3W6"
title = "Pre-test clamp-slip check procedure"
type = "task"
category = "in-progress"
priority = "medium"
points = 3
parent = "01M6W7R06C7F7ZN0RC4CV3NWW5"
reporter = "lognd"
created = "2026-11-08T00:08:19Z"
updated = "2026-11-08T03:12:14Z"
idempotency_key = "sadi-cr3"
labels = ["ws:py", "lctt", "model:sonnet", "creates:python/sadi/labs/lctt/clamp_check.py", "creates:python/tests/labs/lctt/test_clamp_check.py", "creates:docs/lctt/clamp-check.md"]
scope = ["python/sadi/labs/lctt/clamp_check.py", "python/tests/labs/lctt/test_clamp_check.py", "docs/lctt/clamp-check.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R257EXZX1RD7VT3M5GJG"

[[acceptance]]
text = "Procedure: apply a small load, hold N s, unload, repeat; pass/fail from slip detector plus zero return within tolerance; returns Result with advice ('re-tighten clamps')"
bound = true

[[acceptance]]
text = "Exposed as a wizard step 'Setup' sub-check; tested on slipping vs clean simulator scenarios"
bound = false
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). Python: typani Result[T, E] for every fallible operation (exceptions only for programmer bugs), pydantic models, run python -m typani.lint on new code.
