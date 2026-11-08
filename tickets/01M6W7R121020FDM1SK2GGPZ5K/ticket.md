+++
id = "01M6W7R121020FDM1SK2GGPZ5K"
title = "Optional: v3.41 codec (CRC-16/CCITT-FALSE framing)"
type = "task"
category = "in-progress"
priority = "low"
points = 5
parent = "01M6W7R02ZYSESQF4CBEEDYF4K"
reporter = "lognd"
created = "2026-11-08T00:08:17Z"
updated = "2026-11-08T04:34:41Z"
idempotency_key = "sadi-r6"
labels = ["ws:rust", "optional", "unverified-protocol", "model:sonnet", "creates:crates/sadi-proto/src/v3/**", "creates:crates/sadi-proto/tests/vectors_v3.rs", "creates:docs/device/v3.md"]
scope = ["crates/sadi-proto/src/v3/**", "crates/sadi-proto/tests/vectors_v3.rs", "docs/device/v3.md", "docs/index.md", "docs/README.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R0KH8QFP4K9PTM197V9E"

[[acceptance]]
text = "Behind feature v3: CRC-16/CCITT-FALSE (check value 0x29B1), command encode (0x94, 0xF3, 0xF4, 0xF5, 0x93), packet decode (0xF6, 0xF2, 0x61 data)"
bound = true

[[acceptance]]
text = "Passes the v3_41_generic vectors in docs/protocol-vectors.json"
bound = true

[[acceptance]]
text = "Auto-detect probe sketch documented (v1.003 Query then v3 0x94) but not wired into the default build"
bound = true
+++

Secondary and optional. Items 9-11 of protocol.md section 10 stay unverified.

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). Rust: safe code only (no hand-written unsafe), thiserror errors, tracing logs, cargo fmt + clippy -D warnings clean, tests incl. proptest where noted.
