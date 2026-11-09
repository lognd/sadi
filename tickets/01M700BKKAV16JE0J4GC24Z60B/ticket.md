+++
id = "01M700BKKAV16JE0J4GC24Z60B"
title = "ci: cargo fmt drift in sadi-proto codec/v3 command.rs and sadi-py sim.rs"
type = "bug"
category = "done"
outcome = "done"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-09T11:16:08Z"
updated = "2026-11-09T11:22:27Z"
scope = ["crates/sadi-proto/src/codec/command.rs", "crates/sadi-proto/src/v3/command.rs", "crates/sadi-py/src/sim.rs", "changelog.d/01M700BKKAV16JE0J4GC24Z60B.fixed.md"]

[[acceptance]]
text = "given the tree, when cargo fmt --all --check runs, then it reports no diff"
bound = true
+++
