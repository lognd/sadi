+++
id = "01M6W7R2JH4YER4MJPQCTSXSRE"
title = "Run hardware session and fold findings back (needs the physical board)"
type = "task"
category = "todo"
priority = "low"
points = 5
parent = "01M6W7R02ZYSESQF4CBEEDYF4K"
reporter = "lognd"
created = "2026-11-08T00:08:19Z"
updated = "2026-11-08T00:08:19Z"
idempotency_key = "sadi-hw3"
labels = ["ws:rust", "needs-board", "hw-gated", "model:sonnet", "creates:docs/hardware-verification.md", "creates:docs/hardware/**", "creates:crates/sadi-proto/src/codec/**"]
scope = ["docs/hardware-verification.md", "docs/hardware/**", "crates/sadi-proto/src/codec/**"]

[[links]]
kind = "blocked-by"
target = "01M6W7R0VNQVPZ47CD080SB0TA"

[[links]]
kind = "blocked-by"
target = "01M6W7R20Q20BHCEP78X42K86Y"

[[acceptance]]
text = "Every HW1 row has a recorded result with attached capture; wrong assumptions fixed in the codec/session defaults with tests from the real captures"
bound = false

[[acceptance]]
text = "docs/protocol.md section 10 items annotated verified/refuted by the session"
bound = false
+++

Cannot be started until the board is available. Nothing else in the plan is blocked on it: everything is tested against the simulator.

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). Rust: safe code only (no hand-written unsafe), thiserror errors, tracing logs, cargo fmt + clippy -D warnings clean, tests incl. proptest where noted.
