+++
id = "01M6W7R2ZMZSCRWKCRFHAH4MTB"
title = "Crash-recovery tests: kill the process mid-write on every OS"
type = "task"
category = "in-progress"
priority = "critical"
points = 8
parent = "01M6W7R04QJTECCTSV9EY2JADK"
reporter = "lognd"
created = "2026-11-08T00:08:19Z"
updated = "2026-11-08T03:21:57Z"
idempotency_key = "sadi-ds6"
labels = ["ws:store", "fault-injection", "model:sonnet", "creates:python/tests/crash/**", "creates:.github/workflows/crash.yml", "creates:docs/store/crash-testing.md"]
scope = ["python/tests/crash/**", ".github/workflows/crash.yml", "docs/store/crash-testing.md", "docs/store/lock.md", "changelog.d/*HAH4MTB*"]

[[links]]
kind = "blocked-by"
target = "01M6W7R1VQHABR51SH64668M06"

[[links]]
kind = "blocked-by"
target = "01M6W7R1XA74780R58PGCJAR1J"

[[links]]
kind = "blocked-by"
target = "01M6W7R2F3KJWQCWEKZK6BT3MG"

[[acceptance]]
text = "Harness spawns a writer subprocess and SIGKILLs / TerminateProcess it at randomized and failpoint-targeted moments (mid-record, between data fsync and dir fsync, mid-rotate, mid-snapshot rename, mid-manifest)"
bound = true

[[acceptance]]
text = "After each kill, recovery asserts DS1 invariants: all acknowledged (durable_seq) records present, no corrupt record accepted, no session overwritten, snapshot is old-or-new never torn"
bound = false

[[acceptance]]
text = "Runs >= 200 randomized kills per OS in the crash.yml workflow on ubuntu, windows, macos; failures upload the session dir as artifact"
bound = false

[[acceptance]]
text = "Separate test covers power-loss emulation via truncating files to the last fsynced offset"
bound = false
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). Python: typani Result[T, E] for every fallible operation (exceptions only for programmer bugs), pydantic models, run python -m typani.lint on new code.
