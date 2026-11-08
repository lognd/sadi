# sadi-proto serial backend
Status: draft

Owner: ticket ~Q4YBED4. Source: `crates/sadi-proto/src/serial.rs`
(cargo feature `serial`, on by default). The wire protocol is unverified
until a hardware session (protocol.md section 10); nothing here hard-codes
unverified behaviour.

## Types
- `SerialConfig::new(port)` validates and returns `Result`; builders
  `with_baud`, `with_timeout`, `with_rx_limit`, `with_allow_list`. Newtypes
  `BaudRate`, `IoTimeout`, `RxLimit` reject zero.
- Baud default is 12,000,000 bit/s. The FT2232H in 245 FIFO mode ignores
  it; it is only applied to the VCP line setting.
- `list_ports(&[UsbId])` returns `PortCandidate`s whose VID/PID are on the
  list. Default `FTDI_ALLOW_LIST`: 0403:6010, 0403:6014, 0403:6001. The
  list is config (`SerialConfig::allow_list`). On Linux, USB details need the
  `udev` feature (libudev-dev); without it no port is reported as USB.
- `SerialTransport` is move-only (no Clone/Copy) and `#[must_use]`.
  `open(&cfg)` opens a port; `from_port` wraps any open `serialport` handle
  (used by the pty loopback test).

## Semantics
- `read(buf, timeout)`: sets the port timeout per call; a timeout yields
  `TransportError::Timeout`; EOF or a vanished device yields `Closed`.
- `purge`: clears the OS driver RX and TX buffers. Bytes still in the
  device FIFO may arrive afterwards.
- `close` (trait, `&mut self`): releases the port; any later call returns
  `Closed`. `shutdown(self)` is the consuming form.
- RX overflow: before each read the pending byte count is compared with
  `RxLimit` (default 1 MiB). Above it, `read` returns
  `TransportError::Overflow { pending, limit }` without consuming data; call
  `purge` to recover. There is no hidden "Saturation detected" behaviour.

## Future D2XX/libusb backend
`Transport` is the seam. A D2XX or libusb backend would implement the same
trait and be selected by matching the USB description string "SADI 2.0 A"
(reported per channel by the FT2232H) instead of a VCP path. It is not
implemented; `PortCandidate::product` already carries the string.

## Tests
`tests/serial_loopback.rs` runs a pty loopback on unix (skips if ptys are
unavailable) and `#[ignore]`d hardware tests for row 1 of
[hardware-verification.md](../hardware-verification.md); run them with
`cargo nextest run -p sadi-proto --run-ignored only` with a board attached.
