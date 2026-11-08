+++
id = "01M6W7R3J00J2HQ7XPW19WDD6Q"
title = "Live recompute engine: update all results after every captured point"
type = "task"
category = "in-progress"
priority = "high"
points = 5
parent = "01M6W7R06C7F7ZN0RC4CV3NWW5"
reporter = "lognd"
created = "2026-11-08T00:08:20Z"
updated = "2026-11-08T03:34:05Z"
idempotency_key = "sadi-a4"
labels = ["ws:py", "lctt", "model:sonnet", "creates:python/sadi/labs/lctt/live.py", "creates:python/sadi/core/results.py", "creates:python/tests/labs/lctt/test_live.py", "creates:docs/lctt/live-results.md"]
scope = ["python/sadi/labs/lctt/live.py", "python/sadi/core/results.py", "python/tests/labs/lctt/test_live.py", "docs/lctt/live-results.md", "docs/index.md", "docs/README.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R1HWQMSEX38TQM27Y4NY"

[[links]]
kind = "blocked-by"
target = "01M6W7R28HX7237GMXSNQKWT3Y"

[[links]]
kind = "blocked-by"
target = "01M6W7R2F3KJWQCWEKZK6BT3MG"

[[links]]
kind = "blocked-by"
target = "01M6W7R2XY9DB0PFREY9TZ8D2S"

[[links]]
kind = "blocked-by"
target = "01M6W7R3BBDEXG9CPYWTQ7ZKZW"

[[acceptance]]
text = "Pure function recompute(events) -> ResultSet recomputing from RAW-derived points (never from cached display values): calibration slope/intercept, tare, E, r^2, yield each as value, standard uncertainty, 95% interval and plain-language confidence string with class-rule sig figs"
bound = true

[[acceptance]]
text = "Incremental update after each point meets a latency budget (<50 ms for 200 points) and equals the batch result exactly (property test)"
bound = false

[[acceptance]]
text = "Editing a point or window in review recomputes everything consistently; RSS vs Monte Carlo cross-check flag included"
bound = false

[[acceptance]]
text = "Analytic RSS results are computed synchronously and shown instantly; MC and other heavy refinement is delegated to jobs (J3), never run inline"
bound = false
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). Python: typani Result[T, E] for every fallible operation (exceptions only for programmer bugs), pydantic models, run python -m typani.lint on new code.
