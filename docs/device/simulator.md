# SADI v1.003 simulator device
Status: draft

Owner: ticket ~CSWAMV8. Source: `crates/sadi-proto/src/sim/device.rs`.
`SimDevice` is a `Transport` that speaks the real wire protocol
(protocol.md sections 2 and 3, still unverified against hardware), so the
same host code drives it and a board. It uses the codec in both directions:
`Command::decode` for 62-byte frames in, `Packet::encode` for 612-byte
frames out.

## State machine
Firmware states: Booted (1), Stopped (2), Streaming (3). Power-on queues a
boot packet (version 1.003, state 1). Like the firmware, every command is
accepted in every state:

| Command | Effect |
|---|---|
| Start | ranges latched, msgCount zeroed, Streaming; no explicit reply (a Start while Streaming restarts the stream) |
| Stop | Stopped, then a stop-ack (type 2); repeated Stop re-acks |
| Reset | unsent output dropped, Booted, boot packet |
| Query | version packet (type 4) carrying the current state |

The command parser mirrors the firmware: bytes outside a frame that are not
0x55 are dropped, a frame whose tail is not `AA 55 AA 55` drops one byte and
rescans, and frames with an unknown opcode or range code are ignored
(logged at warn). Partial writes are reassembled across `write_all` calls.

## Data packets
While Streaming, packet n (msgCount n, wrapping at 2^32) holds samples
`50n..50n+49`, sample s at stream time `s / rate` (default 50 kHz, so
1000 packets/s). Time restarts at 0 on Start. Each sample takes
`SignalSource::encoder(t)` and `voltage(ch, t)` for channels 0..3. Volts
become raw codes with `raw_from_volts`, the inverse of `codec::convert` for
the range given in Start; out-of-range volts saturate. `SimConfig::
with_adc_mode` picks `Ideal` (default) or `DllCompatible`; the decoder side
must use the same mode. Digital inputs are a constant byte
(`with_digital_inputs`).

## Clocks
- `ClockMode::Virtual` (default): nothing sleeps. A read with queued bytes
  returns them; with none queued it advances the clock to the next packet
  if due within the timeout, otherwise by the full timeout and returns
  `Timeout`. Packet n is due `(n+1)*50/rate` after Start. Output is a pure
  function of the source, config and command sequence.
- `ClockMode::Paced`: the same logic against the wall clock; reads sleep
  until a packet is due (for demos).

At most 1024 undelivered packets are kept; a stalled reader loses the
oldest (visible as a msgCount gap), like an overflowing FIFO.

## Writing a SignalSource and choosing a scenario
Implement `sim::signal::SignalSource` (`voltage(ch, t)`, `encoder(t)`, both
pure functions of time in seconds; `Send`), then:

```rust
let dev = SimDevice::new(Box::new(MySource), SimConfig::default());
```

Built-in scenarios (see [sim-faults.md](sim-faults.md)) are selected by
name: `SimDevice::with_scenario("creeping", SimConfig::default())?`.
Names are in `sim::scenario::SCENARIO_NAMES`; an unknown name returns
`SimError::Scenario`. Seeds live in the scenario's fault plan, so the same
scenario name yields the same bytes every run.

## Not modelled
Hardware timing jitter, FTDI latency and USB chunking, ADS8688 noise beyond
what the source supplies, the 3.41 firmware (see `v3`), and wire-level
fault injection beyond [byte faults](sim-byte-faults.md).

## Tests
`crates/sadi-proto/tests/sim_device.rs`: query/start/stream/stop round trip
through the real `Decoder`, msgCount continuity, sample-by-sample
comparison with the source in both ADC modes, wrong-state commands, partial
and garbage writes, determinism, paced clock.
