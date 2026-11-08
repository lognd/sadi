+++
id = "01M6W7R0KH8QFP4K9PTM197V9E"
title = "Rust workspace scaffold, error types, Transport trait, module stubs"
type = "task"
category = "done"
outcome = "done"
priority = "high"
points = 3
parent = "01M6W7R02ZYSESQF4CBEEDYF4K"
reporter = "lognd"
created = "2026-11-08T00:08:17Z"
updated = "2026-11-08T00:12:29Z"
idempotency_key = "sadi-r1"
labels = ["ws:rust", "model:sonnet", "creates:Cargo.toml", "creates:rust-toolchain.toml", "creates:rustfmt.toml", "creates:clippy.toml", "creates:crates/sadi-proto/Cargo.toml", "creates:crates/sadi-proto/src/lib.rs", "creates:crates/sadi-proto/src/error.rs", "creates:crates/sadi-proto/src/transport.rs", "creates:crates/sadi-proto/src/sim/signal.rs", "creates:crates/sadi-proto/src/codec/mod.rs", "creates:crates/sadi-proto/src/session.rs", "creates:crates/sadi-proto/src/sim/mod.rs", "creates:crates/sadi-proto/src/sim/byte_faults.rs", "creates:crates/sadi-proto/src/serial.rs", "creates:crates/sadi-proto/src/replay.rs", "creates:crates/sadi-proto/src/v3/mod.rs"]
scope = ["Cargo.toml", "rust-toolchain.toml", "rustfmt.toml", "clippy.toml", "crates/sadi-proto/Cargo.toml", "crates/sadi-proto/src/lib.rs", "crates/sadi-proto/src/error.rs", "crates/sadi-proto/src/transport.rs", "crates/sadi-proto/src/sim/signal.rs", "crates/sadi-proto/src/codec/mod.rs", "crates/sadi-proto/src/session.rs", "crates/sadi-proto/src/sim/mod.rs", "crates/sadi-proto/src/sim/byte_faults.rs", "crates/sadi-proto/src/serial.rs", "crates/sadi-proto/src/replay.rs", "crates/sadi-proto/src/v3/mod.rs", "Cargo.lock", "docs/sadi-proto.md", "changelog.d/01M6W7R0KH8QFP4K9PTM197V9E.changed.md", "docs/index.md"]

[[acceptance]]
text = 'Cargo workspace with members = ["crates/*"]; sadi-proto has #![forbid(unsafe_code)]; features: serial (default), v3 (off)'
bound = true

[[acceptance]]
text = "pub trait Transport (Send): write_all, read with timeout -> Result<usize, TransportError>, purge, close, description; documented as the seam for a future D2XX/libusb backend"
bound = true

[[acceptance]]
text = "pub trait SignalSource (sim/signal.rs): voltage(ch, t) and encoder(t) for the simulator; error enums (ProtoError, TransportError) via thiserror"
bound = true

[[acceptance]]
text = "Empty documented stub modules created for every module in the Files list so later tickets own exactly one file/dir each; cargo build/test/clippy pass"
bound = true
+++

Scaffold is the single serialisation point for lib.rs; later Rust tickets must not touch lib.rs or Cargo.toml. The wire protocol is UNVERIFIED until a hardware session (docs/protocol.md section 10); do not hard-code unverified behaviour without a config switch.

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). Rust: safe code only (no hand-written unsafe), thiserror errors, tracing logs, cargo fmt + clippy -D warnings clean, tests incl. proptest where noted.
