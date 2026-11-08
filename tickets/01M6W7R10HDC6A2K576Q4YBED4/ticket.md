+++
id = "01M6W7R10HDC6A2K576Q4YBED4"
title = "serialport backend over the FTDI VCP (Transport impl)"
type = "task"
category = "done"
outcome = "done"
priority = "high"
points = 5
parent = "01M6W7R02ZYSESQF4CBEEDYF4K"
reporter = "lognd"
created = "2026-11-08T00:08:17Z"
updated = "2026-11-08T00:29:58Z"
idempotency_key = "sadi-r5"
labels = ["ws:rust", "unverified-protocol", "model:sonnet", "creates:crates/sadi-proto/src/serial.rs", "creates:crates/sadi-proto/tests/serial_loopback.rs", "creates:docs/device/serial.md"]
scope = ["crates/sadi-proto/src/serial.rs", "crates/sadi-proto/tests/serial_loopback.rs", "docs/device/serial.md", "Cargo.toml", "crates/sadi-proto/Cargo.toml", "Cargo.lock", "crates/sadi-proto/src/error.rs", "docs/sadi-proto.md", "docs/README.md", "docs/hardware-verification.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R0KH8QFP4K9PTM197V9E"

[[acceptance]]
text = "SerialTransport (feature serial) implements Transport via the serialport crate: list_ports filtered on FTDI VID/PID (0403:6010/6014/6001; list is config), open, timeouts, purge (clear), clean close"
bound = true

[[acceptance]]
text = "Baud rate is a config value with a documented default (FIFO mode ignores it); no 'Saturation detected' style behaviour hidden: RX overflow surfaces as a typed error"
bound = true

[[acceptance]]
text = "Pty/loopback test on unix, #[ignore]d hardware tests; compiles on Windows and macOS in CI"
bound = true

[[acceptance]]
text = "Docs explain the seam for a future D2XX/libusb backend (SADI 2.0 A description string match) without implementing it"
bound = true
+++

Use serialport over the FTDI VCP first, behind Transport. Throughput feasibility (612 kB/s) is protocol.md section 10 item 1. The wire protocol is UNVERIFIED until a hardware session (docs/protocol.md section 10); do not hard-code unverified behaviour without a config switch.

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). Rust: safe code only (no hand-written unsafe), thiserror errors, tracing logs, cargo fmt + clippy -D warnings clean, tests incl. proptest where noted.
