# hwprobe: scripted bench probe, raw capture and replay
Status: draft

Owner: ticket ~X42K86Y. Sources: `crates/sadi-proto/examples/hwprobe.rs`,
`crates/sadi-proto/src/replay.rs`. Runs the HW1 checks of
[hardware-verification.md](../hardware-verification.md) without a
hand-written script, and keeps every byte so a field session can be replayed
offline. The wire protocol stays unverified until a board session.

## Usage
`cargo run -p sadi-proto --example hwprobe -- <subcommand> <source> [flags]`

Subcommands: `enumerate`, `query`, `reset-boot-time`,
`stream-60s-with-gap-stats`, `range-sweep`, `encoder-spin`, `digital-in`.

Source (one of): `--sim SCENARIO`, `--replay FILE.bin`, `--port NAME`
(`enumerate` needs none). Flags: `--out DIR` (default `hwprobe-out`),
`--label L`, `--count N`, `--duration-secs S`, `--packets N`,
`--codes 1,2,..` (range-sweep), `--allow-reset`, `--inputs-safe`.

## Safety (first contact with hardware)
- Read-mostly: the handshake is Query only; Reset is sent solely by
  `reset-boot-time`, which refuses to run without `--allow-reset`.
- `range-sweep` with any non-default ADC range refuses without
  `--inputs-safe` (operator confirms inputs are inside the range).
- Gates are checked before any file is created or port opened.
- Streams are always stopped; a failed Stop is reported as an error.

## Outputs (never overwritten)
Per run, in `--out`: `<label>-<subcommand>[-N].bin` (every RX byte, in
order), `.tx.bin` (every byte sent, recorded before sending) and `.json`
(report: tool, subcommand, source, timings, status, error, capture paths and
sizes, and a `data` object with the per-check results such as gap histogram,
boot-time spread, per-channel stats, encoder deltas, PORTD values). Files are
opened with `create_new` (O_EXCL) in append mode; if a name exists the next
`-N` suffix is used. A capture write failure aborts the I/O call.

## Replay
`ReplayTransport` serves a captured RX file in chunks through the normal
`Session`/`Decoder`; writes are counted and ignored, `purge` is a no-op and
reads return `Closed` once the data is exhausted. Use `--replay FILE.bin` or
construct it in a test to turn a field capture into a regression test.
`RecordingTransport<T>` wraps any `Transport` to produce captures.

## CI
`crates/sadi-proto/tests/replay.rs` includes the example and runs every
subcommand against the simulator, plus record/replay and no-overwrite tests.
