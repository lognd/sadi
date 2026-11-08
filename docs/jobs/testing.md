# Job test harness

Status: current

Owner: ~VAX9DG6. Code: `python/sadi/jobs/testing.py`. Tests: `python/tests/jobs/test_harness.py`.
Design source: [concurrency.md](../concurrency.md) section 14. Subject: [jobs.md](jobs.md).

The harness drives a real `JobManager` with a fake clock, a fake event loop and scripted
in-process workers. Tests of supersede, cancel, progress coalescing and state transitions
run with no processes, threads or sleeps, and every run is reproducible from an integer seed.

## Seams

| Real thing | Harness replacement |
|---|---|
| `asyncio` loop (`call_later`, `call_soon_threadsafe`) | `FakeLoop`: FIFO posted-callback queue plus a timer heap on `FakeClock` |
| `time.monotonic` / `time.time_ns` in `sadi.jobs.manager` | `_TimeShim` over `FakeClock`, installed by `JobHarness` |
| `WorkerSlot` (process) | `FakeSlot`, created by overriding `JobManager._spawn` |
| task code in the child | a script: a generator of `Step`, receiving the cancel flag |

Time only moves when a test calls `harness.advance(seconds)`. Nothing runs until the test
steps it: `harness.step(slot)` runs one script step, `harness.settle()` drains posted loop
callbacks.

## Recipe: a deterministic concurrency test

1. Write the task as a script. Each `yield Step(fraction=..., partial=...)` is one progress
   point; the yielded-to value is `True` once a cancel has reached the worker. Return the
   result dict.
2. Build the harness: `h = JobHarness(workers=2)`, `h.register("name", script)`, `h.start()`.
   Call `h.close()` (a fixture) so the real `time` module is restored.
3. Submit with `h.manager.submit(make_spec(n, key=..., task="name", data_version=...))`.
   Job ids are `UUID(int=n)`, so assertions are stable.
4. Step to the exact point of interest with `h.step(i)` or `h.run_slot(i)`, then inject the
   event: `h.manager.cancel(...)`, or submit a newer `data_version` for the same key
   (supersede), or `h.advance(s)` to expire a cancel grace or heartbeat, or
   `h.live_slot(i).crash()`.
5. Assert on `h.outcomes`, `h.envelopes`, `h.manager.metrics()` and `slot.cancel_requests`.
6. For interleavings, hand control to `Interleaver(h, seed)`. `run_until_idle()` picks among
   `h.runnable()` actions with a seeded RNG and records `trace` (a plain `list[str]`).
   Assert invariants for many seeds; to reproduce a failure, call
   `Interleaver.replay(h2, trace)` on a fresh harness. It returns `Err` at the first action
   that is not runnable (divergence).

Fallible harness calls return typani `Result[..., HarnessError]`; assert with
`isinstance(res, Ok)`.

## Scenarios covered

Queued job superseded never starts; progressing job superseded and its late partial discarded;
unacknowledged cancel killed after grace; progress coalescing while the loop is behind;
worker crash fails the job and respawns the slot; task exception and unknown task; silent
worker warns once on fake time; supersede invariants for 60 seeds; trace replay.

## Limitations

- Awaitables are unsupported: `FakeLoop.create_future` and manager `shutdown` raise.
- The `time` shim is module-global while a harness is open; always `close()`.
- `_Job.entered` uses the real clock, so logged durations are approximate.
- Injecting a clock and executor into `JobManager` directly is a follow-up.

## Usage by later tickets

J3, J4 and J5 are expected to write their job-logic tests with this recipe. They have not
yet done so; this page records the contract they build on.
