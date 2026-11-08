+++
id = "01M6W8KJPEKBF9PF987PKS6DHA"
title = "Rust type-driven audit: typestate devices, exhaustive enums, newtypes in sadi-proto"
type = "task"
category = "done"
outcome = "done"
priority = "high"
points = 5
reporter = "lognd"
created = "2026-11-08T00:23:20Z"
updated = "2026-11-08T00:42:01Z"
labels = ["ws:rust", "model:sonnet", "creates:docs/rust-type-design.md"]
scope = ["crates/sadi-proto/src/codec/**", "crates/sadi-proto/src/session.rs", "crates/sadi-proto/src/transport.rs", "crates/sadi-proto/src/error.rs", "docs/rust-type-design.md", "crates/sadi-proto/src/lib.rs", "docs/sadi-proto.md", "python/tests/labs/lctt/test_settle_stream.py"]

[[acceptance]]
text = "Audit landed codec/transport/error for integer-coded kinds, wildcard arms on protocol enums, bare f64/u8 units and channel ids; convert to TryFrom enums and newtypes"
bound = true

[[acceptance]]
text = "Clippy lints enforced crate-wide (wildcard_enum_match_arm, must_use_candidate); compile-fail tests show misuse of device/session handles is rejected"
bound = true

[[acceptance]]
text = "docs/rust-type-design.md states the conventions (typestate session consuming self, linear device handle, newtypes) and is linked from docs/sadi-proto.md"
bound = true
+++

User directive: leverage the type and borrow checker to the fullest. Coordinate with ~SB1MWFD (session typestate) and ~Q4YBED4 (serial); start after ~8XCPH41 lands.
