+++
id = "01M6W7R2M88JFNKRESHJBD8YVD"
title = "sadi-py: simulator and fault-plan bindings"
type = "task"
category = "in-progress"
priority = "medium"
points = 3
parent = "01M6W7R02ZYSESQF4CBEEDYF4K"
reporter = "lognd"
created = "2026-11-08T00:08:19Z"
updated = "2026-11-08T04:05:16Z"
idempotency_key = "sadi-r7b"
labels = ["ws:rust", "fault-injection", "model:sonnet", "creates:crates/sadi-py/src/sim.rs", "creates:crates/sadi-py/python/sadi_py/sim.pyi", "creates:crates/sadi-py/tests/**"]
scope = ["crates/sadi-py/src/sim.rs", "crates/sadi-py/python/sadi_py/sim.pyi", "crates/sadi-py/tests/**", "docs/device/python-binding.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R0XB2WMP03ZGW8XCPH41"

[[links]]
kind = "blocked-by"
target = "01M6W7R0YWS8EXHXFBNZCE4AHC"

[[links]]
kind = "blocked-by"
target = "01M6W7R226VMAMHYPDBQTAS277"

[[acceptance]]
text = "Python can load/validate scenario + FaultPlan JSON (pydantic-friendly dict), set load program at runtime (weight added/removed), inject a slip step now, change seed"
bound = true

[[acceptance]]
text = "Runtime control is thread-safe and tested; invalid plans return a typed error"
bound = true
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). Rust: safe code only (no hand-written unsafe), thiserror errors, tracing logs, cargo fmt + clippy -D warnings clean, tests incl. proptest where noted.
