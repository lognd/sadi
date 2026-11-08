+++
id = "01M6W7R1BJ1PJWFD0FQSB1MWFD"
title = "sadi-proto session: connect/query/reset/start/stop state machine with retries"
type = "task"
category = "done"
outcome = "done"
priority = "high"
points = 5
parent = "01M6W7R02ZYSESQF4CBEEDYF4K"
reporter = "lognd"
created = "2026-11-08T00:08:18Z"
updated = "2026-11-08T00:38:33Z"
idempotency_key = "sadi-r3"
labels = ["ws:rust", "unverified-protocol", "model:sonnet", "creates:crates/sadi-proto/src/session.rs", "creates:crates/sadi-proto/tests/session_mock.rs", "creates:docs/device/session.md"]
scope = ["crates/sadi-proto/src/session.rs", "crates/sadi-proto/tests/session_mock.rs", "docs/device/session.md", "docs/sadi-proto.md", "changelog.d/01M6W7R1BJ1PJWFD0FQSB1MWFD.changed.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R0KH8QFP4K9PTM197V9E"

[[links]]
kind = "blocked-by"
target = "01M6W7R0VNQVPZ47CD080SB0TA"

[[acceptance]]
text = "Session<T: Transport> implements the recommended host sequence of protocol.md section 5 (open, purge, Query, Reset, Query, Start, read blocks, Stop) with configurable retry interval and timeout (defaults per section 2.1, flagged unverified)"
bound = true

[[acceptance]]
text = "read_block yields decoded samples plus gap/dropped-byte stats; state mirrors device byte 2; Start/Stop idempotent per section 2.1"
bound = true

[[acceptance]]
text = "Tested with a scripted mock Transport including timeouts, duplicate acks, truncated Stop packet then stop-ack"
bound = true
+++

Boot time and back-to-back command tolerance are unknown (protocol.md section 10 items 6, 8): timeouts are config, not constants. The wire protocol is UNVERIFIED until a hardware session (docs/protocol.md section 10); do not hard-code unverified behaviour without a config switch.

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). Rust: safe code only (no hand-written unsafe), thiserror errors, tracing logs, cargo fmt + clippy -D warnings clean, tests incl. proptest where noted.
