# Acquisition thread (`sadi_py.acq`)
Status: draft

Owner: ticket ~A8Y67RG. Part of [python-binding](python-binding.md).

`AcqHandle(session, capacity=256)` lifts the streaming stage out of a
`Session` (which reports busy meanwhile) and moves it onto a dedicated Rust
thread named `sadi-acq`. The thread reads blocks and pushes them into a
bounded `sync_channel`. Python pulls with `recv_block(timeout_ms)`, which
releases the GIL while waiting. All code is safe Rust.

## Back-pressure: counted, loud, never silent

When the channel is full the thread holds the block (it is never dropped),
increments `channel_full_waits` once per block, logs an error, and retries
every millisecond. After five seconds `consumer_stalled` is set. If a stop
(or a vanished consumer) arrives while a block is held, the block is counted
in `blocks_lost` and logged as an error.

## Metrics (`AcqHandle.metrics()` / `join()`)

`queue_depth`, `high_water`, `capacity`, `blocks_read`, `blocks_sent`, `gaps`,
`missed_packets`, `dropped_bytes`, `channel_full_waits`,
`channel_full_wait_ms`, `blocks_lost`, `read_timeouts`, `consumer_stalled`,
`state` (`STREAMING|STOPPING|STOPPED|FAILED`) and `error`.
Invariant: `blocks_read == blocks_sent + blocks_lost`.

## Stop and join

`stop()` is non-blocking and idempotent. `join()` stops, waits with the GIL
released, hands the streaming stage back to the session (so `session.stop()`
works) and returns the final metrics. Dropping an unjoined handle stops and
joins the thread. A read error other than a timeout ends the thread in
`FAILED`; queued blocks stay receivable, then `recv_block` raises
`RuntimeError`.

## Tests

Rust: `cargo test -p sadi-py acq::` (a paced real-time simulator with a slow
consumer). Python: `crates/sadi-py/tests/test_acq.py`.
