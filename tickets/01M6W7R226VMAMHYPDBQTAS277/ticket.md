+++
id = "01M6W7R226VMAMHYPDBQTAS277"
title = "sadi-py: PyO3/maturin core bindings (Session, devices, numpy blocks)"
type = "task"
category = "done"
outcome = "done"
priority = "high"
points = 8
parent = "01M6W7R02ZYSESQF4CBEEDYF4K"
reporter = "lognd"
created = "2026-11-08T00:08:18Z"
updated = "2026-11-08T01:16:27Z"
idempotency_key = "sadi-r7"
labels = ["ws:rust", "model:sonnet", "creates:crates/sadi-py/Cargo.toml", "creates:crates/sadi-py/pyproject.toml", "creates:crates/sadi-py/src/lib.rs", "creates:crates/sadi-py/src/device.rs", "creates:crates/sadi-py/src/sim.rs", "creates:crates/sadi-py/python/sadi_py/**", "creates:docs/device/python-binding.md"]
scope = ["crates/sadi-py/Cargo.toml", "crates/sadi-py/pyproject.toml", "crates/sadi-py/src/lib.rs", "crates/sadi-py/src/device.rs", "crates/sadi-py/src/sim.rs", "crates/sadi-py/python/sadi_py/**", "docs/device/python-binding.md", ".github/workflows/ci.yml", "Cargo.lock", "changelog.d/01M6W7R226VMAMHYPDBQTAS277.added.md", "crates/sadi-py/src/acq.rs", "crates/sadi-py/src/errors.rs", "crates/sadi-py/src/convert.rs", "crates/sadi-py/README.md", "crates/sadi-py/src/session.rs", "crates/sadi-py/src/codec.rs", "docs/sadi-proto.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R10HDC6A2K576Q4YBED4"

[[links]]
kind = "blocked-by"
target = "01M6W7R1BJ1PJWFD0FQSB1MWFD"

[[links]]
kind = "blocked-by"
target = "01M6W7R1D3BVJZMCDT7CSWAMV8"

[[acceptance]]
text = "maturin develop builds a wheel exposing sadi_py.open_serial(port, cfg), open_sim(scenario_json, seed), Session.start/stop/read_block, ports(), codec helpers; no unsafe code written by hand"
bound = true

[[acceptance]]
text = "read_block returns raw wire bytes (for the WAL) AND decoded numpy arrays (volts per channel, encoder) in one call; GIL released while blocking in I/O"
bound = true

[[acceptance]]
text = "Rust errors map to a sadi_py exception hierarchy with .kind and .detail; typed .pyi stubs shipped (py.typed)"
bound = true

[[acceptance]]
text = "pytest smoke test against the simulator runs under CI; sim.rs is an empty registered module stub for R7B"
bound = true

[[acceptance]]
text = "lib.rs declares `mod acq;` placeholder so R8 can add acq.rs without touching lib.rs"
bound = true
+++

Python wrapper converting exceptions to typani Result lives in B2, not here. The wire protocol is UNVERIFIED until a hardware session (docs/protocol.md section 10); do not hard-code unverified behaviour without a config switch.

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). Rust: safe code only (no hand-written unsafe), thiserror errors, tracing logs, cargo fmt + clippy -D warnings clean, tests incl. proptest where noted.
