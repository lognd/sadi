# sadi-py Python binding
Status: draft

Owner: ticket ~QTAS277. Source: `crates/sadi-py/` (module `sadi_py._native`,
Python package `sadi_py`). Safe Rust only (`#![forbid(unsafe_code)]`); PyO3
0.30 with abi3-py311, rust-numpy 0.30, built with maturin. The wire protocol
is UNVERIFIED (protocol.md section 10), so every timing and handshake choice is
an optional `SessionConfig` field, never a constant in the binding.

## Move-only handles

sadi-proto encodes phases as distinct types. Python cannot, so one `Session`
class holds a runtime cell: idle stage, busy, or consumed. Each call moves the
stage out, runs the transition and stores the successor. Misuse raises:

- `PhaseError` (kind `phase`): wrong phase; the session is unchanged.
- `ConsumedError` (kind `consumed`): used after `close()`.
- `BusyError` (kind `busy`): another thread is inside a blocking call.

Phases: `DISCONNECTED -connect-> CONNECTED -start-> STREAMING -stop-> STOPPED
-close-> CLOSED`. `restart()` returns STOPPED to CONNECTED and `disconnect()`
returns CONNECTED to DISCONNECTED. Failed transitions return the handle to its
previous phase. `with` stops (if streaming) and closes.

## Blocks

`read_block()` returns a `Block` holding `raw` (every wire byte read since the
previous call, for the WAL) and numpy columns: `volts` (n,4 float64),
`adc_raw` (n,4 uint16), `encoder` (n, int32), per-packet `msg_count` and
`digital_inputs`, plus decoder statistics. No per-sample Python objects are
created. On error, raw bytes stay buffered and arrive with the next block.
`stop()` returns the trailing block. The GIL is released for every blocking
call (`py.detach`).

## Errors

All derive from `SadiError` and carry `.kind` (stable string, listed in
`__init__.pyi`) and `.detail`: ConfigurationError, TransportFailure,
CommandTimeoutError, ReadTimeoutError, UnexpectedStateError, TapError,
CodecFailure, ScenarioFailure, PhaseError, ConsumedError, BusyError. Foreign
`#[non_exhaustive]` transport errors map to kind `other` with a logged warning.

## Entry points

`open_serial(port, cfg=None)`, `open_sim(scenario, seed=None, cfg=None)`
(scenario is JSON text or a builtin name), `ports()`, and codec helpers
`encode_command`, `decode_packet`, `decode_data_packet`, `adc_to_volts`.
Rust enums are mirrored by exhaustive matches without wildcard arms.
`acq.rs` is a placeholder for R8.

## Simulator control (`sadi_py.sim`)

`sim.open(scenario, seed=None)` returns `(Session, SimControl)`; `scenario`
is a builtin name, JSON text or a dict. `SimControl` shares the scenario with
the device behind a mutex, so any thread may call `set_scenario`,
`set_fault_plan`, `set_load_program([(t_s, mass_kg), ...])`, `add_weight(kg)`,
`remove_weight(kg)`, `inject_slip(strain)` and `set_seed(seed)` while the
session streams. "Now" is the latest simulated time the device sampled.
Everything is validated before it replaces state; an invalid plan raises
`ScenarioFailure` (kind `scenario`) and leaves the running scenario unchanged.
`sim.validate_scenario` and `sim.validate_fault_plan` check without opening.
Tests live in `crates/sadi-py/tests/test_sim.py` (run `pytest tests`).

## Build and test

`uvx maturin develop --uv` then `pytest` in `crates/sadi-py`; the CI job
`sadi-py` does this on three OSes. Python-side typani Result wrapping is B2.
