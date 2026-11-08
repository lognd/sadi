+++
id = "01M6W7R1D3BVJZMCDT7CSWAMV8"
title = "Simulator device: protocol-faithful SADI v1.003 Transport"
type = "task"
category = "done"
outcome = "done"
priority = "high"
points = 8
parent = "01M6W7R02ZYSESQF4CBEEDYF4K"
reporter = "lognd"
created = "2026-11-08T00:08:18Z"
updated = "2026-11-08T00:35:19Z"
idempotency_key = "sadi-r4a"
labels = ["ws:rust", "model:sonnet", "creates:crates/sadi-proto/src/sim/mod.rs", "creates:crates/sadi-proto/src/sim/device.rs", "creates:crates/sadi-proto/tests/sim_device.rs", "creates:docs/device/simulator.md"]
scope = ["crates/sadi-proto/src/sim/mod.rs", "crates/sadi-proto/src/sim/device.rs", "crates/sadi-proto/tests/sim_device.rs", "docs/device/simulator.md", "docs/hardware-verification.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R0KH8QFP4K9PTM197V9E"

[[links]]
kind = "blocked-by"
target = "01M6W7R0VNQVPZ47CD080SB0TA"

[[acceptance]]
text = "SimDevice implements Transport: parses 62-byte commands, state machine 1/2/3, emits boot, version, data (msgCount, 50 samples) and stop-ack packets byte-exactly per protocol.md"
bound = true

[[acceptance]]
text = "Two clocks: virtual time (deterministic, fast, for tests) and paced real time (50 kS/s, 1000 packets/s, for demos)"
bound = true

[[acceptance]]
text = "Pulls voltages/encoder from a SignalSource; deterministic with a seed; round-trips through the R2 Decoder in tests"
bound = true

[[acceptance]]
text = "Docs describe how to write a SignalSource and select a scenario"
bound = true
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). Rust: safe code only (no hand-written unsafe), thiserror errors, tracing logs, cargo fmt + clippy -D warnings clean, tests incl. proptest where noted.
