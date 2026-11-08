+++
id = "01M6W7R31CM6MP54RXV36JQFXT"
title = "store/exports: derived exports with provenance, tmp + rename"
type = "task"
category = "in-progress"
priority = "medium"
points = 3
parent = "01M6W7R04QJTECCTSV9EY2JADK"
reporter = "lognd"
created = "2026-11-08T00:08:19Z"
updated = "2026-11-08T03:14:50Z"
idempotency_key = "sadi-ds7"
labels = ["ws:store", "model:sonnet", "creates:python/sadi/store/exports.py", "creates:python/tests/store/test_exports.py", "creates:docs/store/exports.md"]
scope = ["python/sadi/store/exports.py", "python/tests/store/test_exports.py", "docs/store/exports.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R1XA74780R58PGCJAR1J"

[[links]]
kind = "blocked-by"
target = "01M6W7R2F3KJWQCWEKZK6BT3MG"

[[acceptance]]
text = "write_export(session, name, bytes) writes under exports/ with versioned name, tmp + fsync + atomic rename, sidecar provenance (WAL seq range, snapshot hash, code version)"
bound = true

[[acceptance]]
text = "Exports never overwrite; deleting all exports loses no data (test regenerates them from WAL)"
bound = false
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). Python: typani Result[T, E] for every fallible operation (exceptions only for programmer bugs), pydantic models, run python -m typani.lint on new code.
