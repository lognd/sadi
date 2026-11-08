+++
id = "01M6W7R19Y440BDRZJTDK06Q2F"
title = "Concurrency model design: threads, GIL, queues, job lifecycle, versioned results"
type = "docs"
category = "done"
outcome = "done"
priority = "critical"
points = 8
parent = "01M6W7R0G9VM8M2C0QQNX209CZ"
reporter = "lognd"
created = "2026-11-08T00:08:17Z"
updated = "2026-11-08T00:45:36Z"
idempotency_key = "sadi-cc1"
labels = ["ws:conc", "design", "model:fable", "creates:docs/concurrency.md"]
scope = ["docs/concurrency.md", "docs/README.md", "docs/data-safety.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R0HZCA3MXA7231DQHSR7"

[[links]]
kind = "blocked-by"
target = "01M6W7R0T0AC47BJGF2CKTER59"

[[acceptance]]
text = "Thread/process map: Rust acquisition thread (GIL released), WAL writer thread, asyncio loop (I/O only), worker process pool; ownership, queues, bounds, backpressure metrics; explicit rule that data is never dropped on the WAL path"
bound = true

[[acceptance]]
text = "Job lifecycle state machine (queued, running, progressing, superseded, cancelled, done, failed), 'latest wins' supersede rule, cancellation points, progress protocol; results-stream versioning and stale-marker semantics"
bound = true

[[acceptance]]
text = "Deadlock/race analysis: lock order, shutdown order, kill-mid-write interactions with running jobs; the deterministic test strategy used by J2/J5"
bound = true
+++

Fable ticket. Core-critical; implementers must not diverge from this doc.

Suggested model: Fable.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001).
