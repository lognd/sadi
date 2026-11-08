+++
id = "01M6W7R2QFWW5VYSHCVA8Y67RG"
title = "sadi-py acquisition thread: GIL-released reader with bounded channel"
type = "task"
category = "in-progress"
priority = "high"
points = 5
parent = "01M6W7R0G9VM8M2C0QQNX209CZ"
reporter = "lognd"
created = "2026-11-08T00:08:19Z"
updated = "2026-11-08T04:17:48Z"
idempotency_key = "sadi-r8"
labels = ["ws:rust", "ws:conc", "model:sonnet", "creates:crates/sadi-py/src/acq.rs", "creates:crates/sadi-py/tests/acq.rs", "creates:docs/device/acquisition-thread.md"]
scope = ["crates/sadi-py/src/acq.rs", "crates/sadi-py/tests/acq.rs", "docs/device/acquisition-thread.md", "crates/sadi-py/src/session.rs", "crates/sadi-py/python/sadi_py/__init__.py", "crates/sadi-py/python/sadi_py/__init__.pyi", "crates/sadi-py/python/sadi_py/acq.pyi", "crates/sadi-py/tests/test_acq.py", "docs/device/python-binding.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R19Y440BDRZJTDK06Q2F"

[[links]]
kind = "blocked-by"
target = "01M6W7R226VMAMHYPDBQTAS277"

[[acceptance]]
text = "Dedicated Rust thread reads blocks and pushes into a bounded channel; Python consumer calls with the GIL released (py.allow_threads); channel-full is a counted, loud error, never a silent drop"
bound = true

[[acceptance]]
text = "Metrics exposed to Python: queue depth, high-water mark, blocks read, gaps; clean stop/join semantics, no unsafe written by hand"
bound = true

[[acceptance]]
text = "Tested with the simulator at full real-time rate with a deliberately slow consumer"
bound = true
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). Rust: safe code only (no hand-written unsafe), thiserror errors, tracing logs, cargo fmt + clippy -D warnings clean, tests incl. proptest where noted.
