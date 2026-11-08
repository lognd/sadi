+++
id = "01M6W7R1Z1E430ZNZ51V9NMTHC"
title = "Job system core: lifecycle state machine, process pool, cancel and supersede (latest wins)"
type = "task"
category = "done"
outcome = "done"
priority = "high"
points = 8
parent = "01M6W7R0G9VM8M2C0QQNX209CZ"
reporter = "lognd"
created = "2026-11-08T00:08:18Z"
updated = "2026-11-08T01:11:17Z"
idempotency_key = "sadi-j1"
labels = ["ws:conc", "model:sonnet", "creates:python/sadi/jobs/__init__.py", "creates:python/sadi/jobs/state.py", "creates:python/sadi/jobs/manager.py", "creates:python/sadi/jobs/pool.py", "creates:python/tests/jobs/test_manager.py", "creates:docs/jobs/jobs.md"]
scope = ["python/sadi/jobs/__init__.py", "python/sadi/jobs/state.py", "python/sadi/jobs/manager.py", "python/sadi/jobs/pool.py", "python/tests/jobs/test_manager.py", "docs/jobs/jobs.md", "python/sadi/core/errors.py", "docs/README.md", "changelog.d/01M6W7R1Z1E430ZNZ51V9NMTHC.added.md", "docs/index.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R13KW0FFYHZJ7FY28A3R"

[[links]]
kind = "blocked-by"
target = "01M6W7R19Y440BDRZJTDK06Q2F"

[[acceptance]]
text = "JobManager submits CPU-heavy callables to a worker process pool; states per CC1; cancellable via cooperative token plus hard kill timeout; submitting a job with the same key supersedes the previous one (latest wins) and the old result is discarded"
bound = true

[[acceptance]]
text = "Progress callbacks stream from worker to manager; all transitions logged; failures are typed errors, worker crash does not take down the server"
bound = true

[[acceptance]]
text = "Pure-Python module with no web or store imports (clean dependency direction)"
bound = true
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). Python: typani Result[T, E] for every fallible operation (exceptions only for programmer bugs), pydantic models, run python -m typani.lint on new code.
