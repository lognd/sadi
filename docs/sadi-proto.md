# sadi-proto crate scaffold
Status: draft

The Rust workspace lives at the repo root (`members = ["crates/*"]`).
`crates/sadi-proto` is `#![forbid(unsafe_code)]` and has features
`serial` (default) and `v3` (off).

- `error`: `TransportError` and `ProtoError` (thiserror).
- `transport`: the `Transport` trait, the seam for a future D2XX/libusb
  backend (write_all, read with timeout, purge, close, description).
- `sim::signal`: the `SignalSource` trait (`voltage(ch, t)`, `encoder(t)`).
- `codec`: v1.003 commands, packets, ADC scaling and the resync
  decoder; see [device/codec.md](device/codec.md).
- `serial`: serialport backend (feature `serial`); see
  [device/serial.md](device/serial.md).
- `replay`: capture/replay transports and the `hwprobe` example; see
  [device/hwprobe.md](device/hwprobe.md).
- `sim::{physics,signal_faults,scenario}`: simulator physics and fault
  injection; see [device/sim-faults.md](device/sim-faults.md).
- `session`: typestate Disconnected/Connected/Streaming/Stopped handle with
  retries and a raw-RX tap; see [device/session.md](device/session.md).
- Python binding over `session` and the simulator (`crates/sadi-py`); see
  [device/python-binding.md](device/python-binding.md).
- Type-design conventions (typestate, newtypes, lints):
  [rust-type-design.md](rust-type-design.md).
- Empty stubs, one owner ticket each:
  `replay`, `v3`, `sim::byte_faults`.

The wire protocol is unverified until a hardware session; see
protocol.md section 10.
