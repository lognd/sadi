+++
id = "01M6W7R34VRSAYPG4SNQPQKQEK"
title = "Capture modes: human confirm key, auto-capture with max wait, forced-early"
type = "task"
category = "in-progress"
priority = "high"
points = 3
parent = "01M6W7R06C7F7ZN0RC4CV3NWW5"
reporter = "lognd"
created = "2026-11-08T00:08:19Z"
updated = "2026-11-08T03:05:17Z"
idempotency_key = "sadi-s2"
labels = ["ws:py", "lctt", "model:sonnet", "creates:python/sadi/labs/lctt/capture.py", "creates:python/tests/labs/lctt/test_capture.py", "creates:docs/lctt/capture.md"]
scope = ["python/sadi/labs/lctt/capture.py", "python/tests/labs/lctt/test_capture.py", "docs/lctt/capture.md", "docs/README.md", "docs/index.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R1KH0MVS56MX07Q9BX19"

[[links]]
kind = "blocked-by"
target = "01M6W7R2F3KJWQCWEKZK6BT3MG"

[[acceptance]]
text = "Modes: confirm (human accepts when indicator says settled), auto (capture on settle or at max wait, flagged forced-early), fixed-dwell"
bound = true

[[acceptance]]
text = "Capture appends a point event with averaging window referencing raw WAL seq range; points are re-editable (window change) and analysis recomputes from raw"
bound = true

[[acceptance]]
text = "Pressing accept before settled records forced_early=true and warns"
bound = true
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). Python: typani Result[T, E] for every fallible operation (exceptions only for programmer bugs), pydantic models, run python -m typani.lint on new code.
