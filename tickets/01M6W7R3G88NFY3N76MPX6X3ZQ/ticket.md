+++
id = "01M6W7R3G88NFY3N76MPX6X3ZQ"
title = "Progressive background jobs: Monte Carlo interval refinement and GP fit"
type = "task"
category = "in-progress"
priority = "high"
points = 5
parent = "01M6W7R0G9VM8M2C0QQNX209CZ"
reporter = "lognd"
created = "2026-11-08T00:08:20Z"
updated = "2026-11-08T03:08:12Z"
idempotency_key = "sadi-j3"
labels = ["ws:conc", "model:sonnet", "creates:python/sadi/jobs/tasks/mc.py", "creates:python/sadi/jobs/tasks/gp.py", "creates:python/tests/jobs/test_tasks.py", "creates:docs/jobs/tasks.md"]
scope = ["python/sadi/jobs/tasks/mc.py", "python/sadi/jobs/tasks/gp.py", "python/tests/jobs/test_tasks.py", "docs/jobs/tasks.md", "python/sadi/jobs/tasks/__init__.py", "python/sadi/jobs/tasks/_drive.py"]

[[links]]
kind = "blocked-by"
target = "01M6W7R2A727G6H66B6FBSDE1R"

[[links]]
kind = "blocked-by"
target = "01M6W7R2GTD88HAHEJ4VAX9DG6"

[[links]]
kind = "blocked-by"
target = "01M6W7R39TND6SN4ENN93ZD322"

[[acceptance]]
text = "MC job emits progressive intervals as samples accumulate (interval tightens, progress fraction), stops at target samples or when superseded; GP fit/suggestion job likewise supersedable"
bound = true

[[acceptance]]
text = "A new captured point supersedes in-flight jobs for stale data; deterministic via J2 harness and seeds; final MC result matches a single-shot run with the same seed"
bound = true
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). Python: typani Result[T, E] for every fallible operation (exceptions only for programmer bugs), pydantic models, run python -m typani.lint on new code.
