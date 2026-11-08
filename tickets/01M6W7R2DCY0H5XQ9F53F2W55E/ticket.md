+++
id = "01M6W7R2DCY0H5XQ9F53F2W55E"
title = "WAL writer thread: bounded queue, backpressure metrics, fsync off the acquisition path"
type = "task"
category = "done"
outcome = "done"
priority = "critical"
points = 5
parent = "01M6W7R0G9VM8M2C0QQNX209CZ"
reporter = "lognd"
created = "2026-11-08T00:08:19Z"
updated = "2026-11-08T01:16:18Z"
idempotency_key = "sadi-ds8"
labels = ["ws:conc", "data-safety", "model:sonnet", "creates:python/sadi/store/writer_thread.py", "creates:python/tests/store/test_writer_thread.py", "creates:docs/store/writer-thread.md"]
scope = ["python/sadi/store/writer_thread.py", "python/tests/store/test_writer_thread.py", "docs/store/writer-thread.md", "python/sadi/store/wal.py", "docs/store/wal.md", "docs/index.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R19Y440BDRZJTDK06Q2F"

[[links]]
kind = "blocked-by"
target = "01M6W7R1VQHABR51SH64668M06"

[[acceptance]]
text = "Dedicated thread owns the WalWriter; producers enqueue into a bounded queue; a slow fsync applies backpressure (blocks or reports) and exposes metrics (depth, wait time, fsync latency), but NEVER drops data"
bound = true

[[acceptance]]
text = "durable_seq published monotonically; shutdown drains the queue; error in the writer stops acquisition loudly with a typed error"
bound = true

[[acceptance]]
text = "Tested with slow-fsync and ENOSPC fault injection"
bound = true
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). Python: typani Result[T, E] for every fallible operation (exceptions only for programmer bugs), pydantic models, run python -m typani.lint on new code.
