# Simulator byte-level faults
Status: draft

`sim::byte_faults::FaultyTransport<T: Transport>` wraps any transport
(`SimDevice`, serial, replay) and corrupts what the host reads, to test
the resync decoder, session retries and timeout handling. Writes, purge,
close pass straight through; `description()` is `faulty(<inner>)`.

## Rates
`ByteFaultPlan` is serde (`deny_unknown_fields`, every field optional,
default = no faults). Rates are `Probability` newtypes validated to
`[0, 1]`; out-of-range or non-finite JSON is rejected at parse time.

| field | scope | effect |
|---|---|---|
| `seed` | - | seeds the fault stream (u64) |
| `drop` | per byte | byte vanishes |
| `duplicate` | per byte | byte delivered twice |
| `flip` | per byte | one random bit inverted |
| `truncate` | per read chunk | chunk cut at a random point, tail lost |
| `stall` | per read | read returns `Timeout` without consuming data |
| `short_read` | per read | fewer bytes than available returned (none lost) |

If every byte of a chunk is lost the read reports `Timeout`, as a real
port with no data would.

## JSON
```json
{ "seed": 7, "drop": 0.002, "flip": 0.001, "stall": 0.05, "short_read": 0.2 }
```
This object is its own document, parsed as `ByteFaultPlan`. It is a
sibling of the signal `FaultPlan` ([sim-faults.md](sim-faults.md)), not a
field of it: signal faults are a pure function of time, byte faults are
stateful per stream, and `FaultPlan` rejects unknown fields. Bindings that
want both carry two objects, e.g. `{"signal": <FaultPlan>, "bytes":
<ByteFaultPlan>}`.

## Determinism
Draws come from a counter-based splitmix64 stream keyed by `seed` (the
same mixer as the signal noise). Draw order is fixed (stall, truncate,
then drop/flip/duplicate per byte, then short_read), so the same seed,
plan and inner byte stream give identical faults. `stats()` returns
counts of each injected fault.

## Usage
```rust
let plan = ByteFaultPlan::default().with_seed(7).with_flip(Probability::new(0.001)?);
let t = FaultyTransport::new(SimDevice::new(src, SimConfig::default()), plan);
```
Tests: `crates/sadi-proto/tests/byte_faults.rs`.
