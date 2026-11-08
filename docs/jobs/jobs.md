# Job system core

Status: current

Owner: ~V9NMTHC. Code: `python/sadi/jobs/` (`state.py`, `pool.py`, `manager.py`).
Tests: `python/tests/jobs/test_manager.py`. Deterministic test harness: [testing.md](testing.md). Design source: [concurrency.md](../concurrency.md).

The job system runs CPU-heavy analysis off the asyncio loop in spawn-context worker
processes. It is pure Python and imports neither `sadi.web` nor `sadi.store`; workers
never import `sadi.store` (checked by a test).

## Lifecycle

States (`JobState`, exhaustive enum with a total transition table):

    QUEUED -> RUNNING -> PROGRESSING -> DONE
                  |           |-> FAILED | CANCELLED | SUPERSEDED
    QUEUED -> CANCELLED | SUPERSEDED   (never sent to a worker)

Terminal states are sinks. Every transition is logged with the job id, key, data version,
old and new state and time spent in the old state.

## Submitting and latest-wins

`JobManager.submit(JobSpec)` returns `Result[JobId, JobError]`. A `JobSpec` names its task
as an import path `module:function` (the function is `fn(inputs, CancelToken) -> dict`);
callables are never pickled. Submitting a second job with the same `key` supersedes the live
one: a queued job is removed, a running one is cancelled. A result that arrives from a
superseded or cancelled job is discarded (`JobOutcome.discarded` / `result is None`) and
never published. A `stale` envelope is emitted for the key when a newer data version arrives.

## Cancel and hard kill

`cancel` / `cancel_key` send a cooperative Cancel; tasks poll `CancelToken.cancelled` or
`CancelToken.check(fraction, partial)`. If the task has not stopped within the grace
(`CANCEL_GRACE_S` = 0.5 s) the worker is killed, the job finishes as `CANCELLED`
(`killed=True`) and the slot is respawned.

## Workers and priority

Workers are `sadi-worker-<n>` processes (spawn context) with a command pipe in and an
event pipe out; a watchdog exits the worker when the parent goes away. With more than one
worker, slot 0 is reserved for `interactive` jobs; with one worker there is no reservation.
A worker crash fails only its job with `JobCode.WORKER_CRASHED` and the slot is respawned.

## Progress and results

Workers emit `Progress` events (throttled by `progress_interval_ms`, monotonic fraction).
The manager coalesces to the latest per slot. Results use `ResultEnvelope` with
`data_version`, a per-key monotone `result_version` and state `analytic|refining|final|stale`.
An optional `sink` callback receives envelopes; `on_outcome` receives each `JobOutcome`.

Concrete progressive tasks (Monte Carlo and GP fit) are described in [tasks.md](tasks.md).

## Threading

`JobManager` is loop-thread only (asserted). Pump threads post to the loop via
`call_soon_threadsafe`; the only lock is a leaf lock around each slot's pending-progress cell.

## Shutdown

`await shutdown(grace_s)` cancels all live jobs, waits one shared grace, kills survivors,
asks workers to exit and joins them. Later `submit` returns `JobCode.SHUTTING_DOWN`.

## Open questions

- `result_version` is a manager-local counter per key until the store supplies the real one.
- Timing constants live in `jobs/state.py`, not `core/limits.py`.
- Job error codes were added to `core/errors.py` (`UNKNOWN`, `WORKER_CRASHED`, `TASK_FAILED`,
  `SLOT_BUSY`, `SHUTTING_DOWN`).
