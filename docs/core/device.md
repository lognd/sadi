# Device service and session phases

Status: current

Owner: ~GX511CP. Code: `python/sadi/core/device.py`,
`python/sadi/core/phases.py`. Tests: `python/tests/core/test_device.py`,
`python/tests/core/test_phases.py` (run against the simulator; they skip when
the `sadi_py` extension is not built). Binding: [python-binding](../device/python-binding.md),
protocol session: [session](../device/session.md).

## Phase classes (`phases.py`)

One class per session phase wraps the native `sadi_py.Session`:

| Class | Methods | Successor |
|-------|---------|-----------|
| `Disconnected` | `connect`, `close` | `Connected` |
| `Connected` | `query`, `start`, `disconnect`, `close` | `Streaming`, `Disconnected` |
| `Streaming` | `read_block`, `stop` | `Stopped` (plus trailing block) |
| `Stopped` | `restart`, `close` | `Connected` |

Calls invalid in a phase do not exist on its class, so misuse fails type
checking. A successful transition consumes the old object (`spent` is True);
using it again raises `SpentPhaseError`, a programmer bug. A failed transition
returns `Err` and leaves the object usable so the caller can retry.

Every fallible method returns a typani `Result[T, DeviceError]`. sadi_py
exceptions are converted by kind: timeouts -> `TIMEOUT`, closed/io ->
`DISCONNECTED`, config/scenario -> `NOT_FOUND`, codec (frame decode) -> `BAD_DATA`, everything else ->
`PROTOCOL`; the error's `hint` is the plain 'what to do' text. The native
kinds `phase`, `consumed` and `busy` are programmer bugs and are re-raised.

## DeviceService (`device.py`)

`DeviceService(DeviceSource)` owns one session. A `DeviceSource` is the
simulator (`kind="sim"`, scenario, seed) or a serial port (`kind="serial"`;
`port=None` auto-detects the first FTDI device, vendor id 0x0403).

- `open()`, `reconnect()` (exponential `Backoff`: `base_s * 2**attempt`, capped
  at `max_s`, `attempts` tries), `close()`.
- `start_streaming()` starts the `sadi-reader` thread; `stop_streaming()` joins
  it and returns the still-queued blocks plus the trailing block, then returns
  the session to Connected.
- `status`: `connected` (serial up), `simulated` (simulator up), `error`
  (not open, open failed, or reader faulted).

## Reader queue and overflow

The reader thread pushes `Block`s into a bounded `queue.Queue` (default 256
blocks, see [concurrency](../concurrency.md) section 3). A block is never
silently dropped. If the queue is full the reader stops, keeps the block in
hand, logs an error, sets status `error` and `fault` to `ReaderOverflow`;
`next_block()` hands out the queued blocks and the held block first, then
returns `Err(ReaderOverflow)`. Device errors in the reader surface the same
way. Raw bytes stay buffered in the native session.

## Not covered

`sadi_py` is not yet a declared dependency of `python/pyproject.toml`; build it
with `maturin develop` in `crates/sadi-py`. The WAL tap and pipeline wiring
belong to ~60ZNFTD.
