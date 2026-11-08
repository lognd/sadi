+++
id = "01M6W7RAY4KTF866Q0Y7B4SZGG"
title = "Race/deadlock suite incl. kill-mid-write while jobs are running"
type = "task"
category = "done"
outcome = "done"
priority = "critical"
points = 8
parent = "01M6W7R0G9VM8M2C0QQNX209CZ"
reporter = "lognd"
created = "2026-11-08T00:08:27Z"
updated = "2026-11-08T06:20:49Z"
idempotency_key = "sadi-j5"
labels = ["ws:conc", "ws:qa", "fault-injection", "model:sonnet", "creates:python/tests/concurrency/**", "creates:docs/concurrency-testing.md"]
scope = ["python/tests/concurrency/**", "docs/concurrency-testing.md", "docs/README.md", "docs/index.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R2DCY0H5XQ9F53F2W55E"

[[links]]
kind = "blocked-by"
target = "01M6W7R2GTD88HAHEJ4VAX9DG6"

[[links]]
kind = "blocked-by"
target = "01M6W7R2QFWW5VYSHCVA8Y67RG"

[[links]]
kind = "blocked-by"
target = "01M6W7R2ZMZSCRWKCRFHAH4MTB"

[[links]]
kind = "blocked-by"
target = "01M6W7RAK3KCB1G87VKETJKV0D"

[[acceptance]]
text = "Stress tests under seeded interleavings: capture during refinement, supersede storms, cancel during write, slow fsync with full queue, shutdown with live jobs; detect deadlock via timeouts and lock-order checks"
bound = true

[[acceptance]]
text = "Kill (SIGKILL/TerminateProcess) the whole app mid-WAL-write while MC/GP jobs run: recovery keeps every acknowledged record, jobs restart from raw, no torn state"
bound = true

[[acceptance]]
text = "asyncio loop-lag assertion (<50 ms p99) while acquisition at 50 kS/s and jobs are active"
bound = true
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). Python: typani Result[T, E] for every fallible operation (exceptions only for programmer bugs), pydantic models, run python -m typani.lint on new code.
