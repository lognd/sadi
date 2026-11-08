+++
id = "01M6W7R0VNQVPZ47CD080SB0TA"
title = "sadi-proto codec: v1.003 commands, packets, ADC scaling, resync decoder"
type = "task"
category = "done"
outcome = "done"
priority = "high"
points = 8
parent = "01M6W7R02ZYSESQF4CBEEDYF4K"
reporter = "lognd"
created = "2026-11-08T00:08:17Z"
updated = "2026-11-08T00:19:32Z"
idempotency_key = "sadi-r2"
labels = ["ws:rust", "unverified-protocol", "model:sonnet", "creates:crates/sadi-proto/src/codec/**", "creates:crates/sadi-proto/tests/vectors.rs", "creates:docs/device/codec.md"]
scope = ["crates/sadi-proto/src/codec/**", "crates/sadi-proto/tests/vectors.rs", "docs/device/codec.md", "crates/sadi-proto/Cargo.toml", "Cargo.lock", "docs/sadi-proto.md", "docs/index.md", "changelog.d/01M6W7R0VNQVPZ47CD080SB0TA.changed.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R0KH8QFP4K9PTM197V9E"

[[acceptance]]
text = "Encodes the four 62-byte host commands (Start carries ADC range codes) and validates ranges {0,1,2,3,5,6,7,11,15}"
bound = true

[[acceptance]]
text = "Streaming Decoder: push bytes, yields Result<Packet> for type 4 version, type 5 data (50 samples x i32 encoder + 4 x u16 BE ADC), type 2 stop-ack; resyncs on 0x55 + AA55AA55 tail at +608; counts dropped bytes and msgCount gaps"
bound = true

[[acceptance]]
text = "ADC conversion in two modes, bug-compatible (DLL) and ideal, selected explicitly; passes every v1_003_mom vector in docs/protocol-vectors.json in both modes"
bound = true

[[acceptance]]
text = "proptest: never panics on arbitrary bytes; decoding a stream with injected garbage/dropped bytes recovers all later intact packets"
bound = true
+++

Primary target is the lab board (FTDI parallel FIFO, 612-byte data packets, 50 kS/s, no CRC). Block size and sample rate are configuration (open question Q4 default: configurable, 50 kS/s, 2500-sample display blocks). The wire protocol is UNVERIFIED until a hardware session (docs/protocol.md section 10); do not hard-code unverified behaviour without a config switch.

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). Rust: safe code only (no hand-written unsafe), thiserror errors, tracing logs, cargo fmt + clippy -D warnings clean, tests incl. proptest where noted.
