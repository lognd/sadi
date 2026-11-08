# Signal injection bench

Status: current

Parent: [AD3 Digilent DWF binding](ad3.md)

Verification: exercised only against `FakeDwf` (no hardware). The real SADI board
pin mapping is unknown; see ticket ~2GQ2J53.

`sadi.bench.inject` drives any `DwfBackend` (real `CtypesBackend` or the in-memory
`sadi.bench.ad3.fake.FakeDwf`) to inject analog signals toward a SADI board and
capture scope readings. The same test code runs against hardware later.

## FakeDwf

Deterministic, hardware-free, identical on every OS. Analog out channels generate
dc, sine, square, triangle, ramp up/down or a custom buffer (`set_custom`).
Scope channel `s` samples the out channel `FakeConfig.wiring[s]` as
`gain * (signal + noise) + offset_v`, minus the scope offset, clipped to the
scope range. Noise is gaussian from `random.Random(seed)`, so equal seeds give
equal captures. Each acquisition starts at t = 0. Unsupported functions or
modes return `Err(CALL_FAILED)`.

## Pin mapping

`PinMap` (pydantic, frozen, extra forbidden) holds a `SignalRoute` for `lvdt`
and `load`: the AD3 `out_channel` and optional `scope_channel`. The two routes
must use different out channels. Nothing is hard-coded to a board.

## Helpers

`inject_lvdt` (sine), `inject_dc` (load level), `stop_injection`, `capture`;
all return typani `Result[..., DwfError]`.

## SADI ADC loopback

`volts_to_counts` / `counts_to_volts` model the ideal bipolar 16-bit ADS8688
conversion (see [protocol](../protocol.md) section 4). The CI loopback test
injects a sine through `FakeDwf`, captures it and compares the resulting counts
with the analytic counts. The compiled `sadi_py` simulator is a maturin extension
and is not required in CI, so this model stands in for it.
