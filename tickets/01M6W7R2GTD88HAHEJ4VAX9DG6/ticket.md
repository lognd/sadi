+++
id = "01M6W7R2GTD88HAHEJ4VAX9DG6"
title = "Deterministic job test harness: fake clock, controllable scheduler, inline executor"
type = "task"
category = "done"
outcome = "done"
priority = "high"
points = 5
parent = "01M6W7R0G9VM8M2C0QQNX209CZ"
reporter = "lognd"
created = "2026-11-08T00:08:19Z"
updated = "2026-11-08T01:21:46Z"
idempotency_key = "sadi-j2"
labels = ["ws:conc", "qa", "model:sonnet", "creates:python/sadi/jobs/testing.py", "creates:python/tests/jobs/test_harness.py", "creates:docs/jobs/testing.md"]
scope = ["python/sadi/jobs/testing.py", "python/tests/jobs/test_harness.py", "docs/jobs/testing.md", "docs/jobs/jobs.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R1Z1E430ZNZ51V9NMTHC"

[[acceptance]]
text = "Harness lets tests step job progress, inject cancellation/supersede at exact points, control time, and replay a recorded interleaving seed; no sleeps in tests"
bound = true

[[acceptance]]
text = "Documented recipe for writing a deterministic concurrency test; used by J3, J4, J5"
bound = true
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). Python: typani Result[T, E] for every fallible operation (exceptions only for programmer bugs), pydantic models, run python -m typani.lint on new code.
