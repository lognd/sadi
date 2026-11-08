# Rust type-design conventions (sadi-proto)
Status: draft

How `crates/sadi-proto` uses the type and borrow checker so misuse fails to
compile. Overview of the crate: [sadi-proto.md](sadi-proto.md); session
details: [device/session.md](device/session.md).

## Conventions

- Typestate session, consuming self. `Disconnected -> Connected ->
  Streaming -> Stopped` are distinct types; transitions take `self` and
  return the next state. A failed transition returns `TransitionError<H>`
  carrying the old handle back, so nothing is lost or duplicated.
- Linear (move-only) handles. Session and device handles are not `Clone`
  or `Copy`; using a stale handle after a transition is E0382. The
  `compile_fail` doctests in `session.rs` pin this (E0599 for calling a
  method in the wrong state, E0382 for use after move).
- Integers cross the codec edge once. Wire bytes become enums through
  `TryFrom<u8>` (`AdcRange`, `AdcChannel`, private `Opcode` and
  `PacketType`) and leave through `From<..> for u8`. No integer-coded
  kinds exist past `codec`. `DeviceState` is total (`From<u8>`) and keeps
  unrecognised bytes as `Unknown(u8)` on purpose.
- Newtypes for units and ids: `Volts`, `AdcChannel`, `MaxAttempts`, and the
  session timeout/interval types. `Sample::raw` and `Sample::volt` take an
  `AdcChannel`, never a bare integer (compile_fail doctest in
  `codec/packet.rs`).
- Exhaustive matches, no wildcard arms on protocol enums. Enforced by
  `clippy::wildcard_enum_match_arm` (deny, `lib.rs`). Adding a variant
  breaks every match until it is handled.
- `#[non_exhaustive]` only where growth is expected and callers must not
  match exhaustively: the error enums (`CodecError`, `TransportError`,
  `ProtoError`). Protocol enums (`Command`, `Packet`, `AdcRange`) stay
  exhaustive on purpose.
- `#[must_use]` on pure accessors and conversions, enforced by
  `clippy::must_use_candidate` (deny, `lib.rs`). `#![forbid(unsafe_code)]`
  at crate root and in `codec`.

## Audit result

Remaining deliberate gaps: `convert`, `AdcRange::full_scale_volts` and
`Sample::volts` still return bare `f64` because the simulator and
integration tests (outside this ticket's scope) consume them; `Volts` is
used by the new `Sample::volt`. `Command::Start` still takes
`[AdcRange; 4]` rather than a per-channel map. Migration is follow-up work.
