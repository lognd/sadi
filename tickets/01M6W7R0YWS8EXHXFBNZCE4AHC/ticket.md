+++
id = "01M6W7R0YWS8EXHXFBNZCE4AHC"
title = "Simulator byte-level faults: dropped, duplicated, corrupted, truncated bytes"
type = "task"
category = "done"
outcome = "done"
priority = "medium"
points = 3
parent = "01M6W7R02ZYSESQF4CBEEDYF4K"
reporter = "lognd"
created = "2026-11-08T00:08:17Z"
updated = "2026-11-08T00:56:39Z"
idempotency_key = "sadi-r4c"
labels = ["ws:rust", "fault-injection", "model:sonnet", "creates:crates/sadi-proto/src/sim/byte_faults.rs", "creates:crates/sadi-proto/tests/byte_faults.rs", "creates:docs/device/sim-byte-faults.md"]
scope = ["crates/sadi-proto/src/sim/byte_faults.rs", "crates/sadi-proto/tests/byte_faults.rs", "docs/device/sim-byte-faults.md", "crates/sadi-proto/src/sim/mod.rs", "crates/sadi-proto/src/sim/signal_faults.rs", "docs/README.md", "docs/device/simulator.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R0KH8QFP4K9PTM197V9E"

[[acceptance]]
text = "FaultyTransport<T: Transport> wraps any Transport with seeded drop/duplicate/flip/truncate/stall/short-read faults, serde configurable"
bound = true

[[acceptance]]
text = "Test with a mock inner transport proves faults are reproducible per seed"
bound = true

[[acceptance]]
text = "Documented rates and how they map to FaultPlan JSON"
bound = true
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). Rust: safe code only (no hand-written unsafe), thiserror errors, tracing logs, cargo fmt + clippy -D warnings clean, tests incl. proptest where noted.
