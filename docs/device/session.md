# sadi-proto session
Status: draft

Owner: ticket ~SB1MWFD. Source: `crates/sadi-proto/src/session.rs`.
Implements the protocol.md section 5 host sequence. Every timing and skip
rule is UNVERIFIED until a hardware session (protocol.md section 10), so
all of them are configuration (`SessionConfig`), not constants.

## Phases

`Disconnected -> Connected -> Streaming -> Stopped`, each a distinct
move-only `#[must_use]` type. A phase change consumes the handle and
returns `Result<Next, TransitionError<Previous>>`; on failure
`TransitionError::into_handle` returns the previous phase so the device is
never lost. `query` and `reset` are not phase changes and take `&mut self`
on `Connected`. Calls invalid in a phase do not exist there; the module
docs carry `compile_fail` examples (read before start, stop twice, start
while streaming, reuse after transition).

## Sequence

`connect`: purge, reset the decoder, Query, Reset (waits for a Version
packet in state Booted), Query (state must be Booted, else
`UnexpectedState`). `Handshake::QueryOnly` skips the Reset. `start` sends
Start; success is the first packet with state Running (no explicit ack).
`stop` sends Stop; success is a StopAck. Data packets that arrive during
Start/Stop are kept and returned by `Stopped::take_trailing` or the next
`read_block`.

## Retries (defaults from the DLL, unverified)

| Command | Retry interval | Timeout |
|---------|----------------|---------|
| Query   | 200 ms         | 2 s     |
| Reset   | 200 ms         | 2 s     |
| Start   | 20 ms          | 1 s     |
| Stop    | 2 ms           | 1 s     |

`CommandPolicy` also carries a `MaxAttempts` cap. `ReadTimeout` (default
500 ms, our choice, not from the DLL) bounds `read_block`. Newtypes reject
zero values and an interval longer than its timeout.

## Idempotence

With `Idempotence::SkipIfAlready` (default) Start is not sent when the last
observed state is Running, and Stop is not sent when it is Stopped, as in
momLab.dll. `AlwaysSend` disables this. The mirrored state is device
packet byte 2, updated from every decoded packet.

## Raw tap and blocks

`Disconnected::with_tap` installs a `RawTap` called with every raw RX
chunk before decoding, for the WAL (data-safety.md). If the tap fails the
bytes are still decoded, then `SessionError::Tap` is returned so
acquisition stops loudly. `read_block` returns data packets plus
`BlockStats` (dropped bytes, malformed, gap events, missed packets) since
the previous block. Bytes dropped during Start/Stop are counted in the
next block.

## Known limits

- Timing is wall clock with `Transport::read` timeouts; tests use real
  time with millisecond-scale timeouts.
- Version/state reply semantics for Start (state 3 as the ack) are inferred
  from the DLL, not observed on hardware.
