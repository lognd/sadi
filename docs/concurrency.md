# Concurrency model: threads, GIL, queues, job lifecycle, versioned results

Status: current

Owner ticket: CC1 ~DK06Q2F (design document). Implementing tickets: R8
~A8Y67RG (acquisition thread), DS8 ~3F2W55E (writer thread), B3 ~60ZNFTD
(pipeline), J1 ~V9NMTHC (job core), J2 ~VAX9DG6 (deterministic harness),
J3 ~PX6X3ZQ (progressive jobs), J4 ~ETJKV0D (results stream), J5 ~7B4SZGG
(race/deadlock suite), F16 ~4XEGRNJ (results-stream client). Each
implements the section that names it, exactly as written; a deviation is a
change to this file in the same ticket, not a silent divergence. The
durability rules this document relies on are owned by
[data-safety.md](data-safety.md) (cited as DS section N) and are not
restated here.

The user's mandate, which every decision below serves:

- Nothing blocks the user. The asyncio loop and the browser never wait on
  a disk, a device or a computation.
- Monte Carlo and refits run in a cancellable background worker pool;
  a newer request always supersedes an older one ("latest wins").
- Data is NEVER lost on the WAL path. No queue between the device and the
  WAL drops, coalesces or reorders.
- Nothing is displayed as data until `durable_seq` covers it (DS I6).

"Non-blocking" is a statement about the loop and the UI. Dedicated threads
block on their own queues on purpose; that is how backpressure propagates
towards the device without ever dropping a byte.

## 0. Contents

1. Thread and process map
2. Ownership table
3. Queues, bounds and backpressure
4. The GIL and the Rust boundary
5. Metrics
6. Job lifecycle state machine
7. Latest wins: supersede, cancel, kill
8. Progress protocol
9. Versioned results stream and stale markers
10. Lock order
11. Shutdown order
12. Kill-mid-write with running jobs
13. Deadlock and race analysis
14. Deterministic test strategy (J2, J5)
15. Module map and public signatures
16. Open points

## 1. Thread and process map

One `sadi` process plus a pool of worker processes. Every thread has a
fixed name (shown in logs and in `/api/metrics`).

```
process: sadi (launcher, FastAPI, store)
  main thread            asyncio loop (uvicorn). I/O only: HTTP, WebSocket,
                         JobManager state, ResultsBroadcaster, signal handlers.
                         Owns ALL job and results state; no lock needed for it.
  sadi-acq               Rust thread (sadi-py, no GIL). Owns the Transport and
                         the Decoder. Reads bytes, frames packets, groups them
                         into RawBlocks, sends them on the acquisition channel.
                         Executes device commands sent on the command channel.
  sadi-pipeline          Python thread (B3). Pulls RawBlocks (GIL released
                         while waiting), submits RAW_BLOCK/RAW_JUNK records to
                         the writer, holds the pending map, applies the display
                         gate, runs the streaming analysis stage (decode,
                         settle detector), posts frames and events to the loop.
  sadi-wal-writer        Python thread (DS8, DS 7). Owns WalWriter and the
                         segment fd. Group commit, durable_seq, metrics.
  sadi-analytic          ThreadPoolExecutor(max_workers=1). Runs the lab's
                         analytic recompute() (fast closed-form) per data
                         version, latest wins. Never the MC work.
  sadi-job-pump-<n>      One Python thread per worker slot. Blocks on the
                         worker's event pipe and posts events to the loop.
process: sadi-worker-<n>  (multiprocessing "spawn" context; N = WORKER_COUNT)
  main thread            Receives JobSpec, runs the task function with a
                         CancelToken, emits progress and a terminal event.
  watchdog               Blocks on the command pipe; on EOF (parent died)
                         calls os._exit(0) so no orphan survives a kill.
```

Decisions:

- Spawn, never fork. The parent holds threads and locks (writer, pipeline,
  Rust); forking such a process is undefined for the child. Spawn is also
  the only context on Windows, so behaviour is identical on all three OS.
- Worker processes never open anything under the session directory and
  never import `sadi.store`. They receive inputs by value (pydantic
  `model_dump()`), return results by value. J5 asserts this (DS 12.2,
  `kill-during-jobs`).
- `WORKER_COUNT = max(1, min(4, os.cpu_count() - 1))`, overridable by
  `--workers`. One slot is always reserved for the key class `interactive`
  (section 7.4) so a long refit cannot starve a point's interval
  refinement.
- The analytic recompute runs on a thread, not a worker: it is a few ms of
  numpy, its input is the full point list and its latency defines how fast
  the UI reacts after a capture. Shipping it to a process would cost more
  in pickling than it saves.
- The streaming analysis stage (decode, settle detector, slip detector)
  runs on `sadi-pipeline`, synchronously after the gate. It is O(samples)
  with numpy and well under budget at 1000 packets/s. If a profile shows
  otherwise, the stage moves to its own thread fed by a second
  never-drop queue; the gate stays where it is.

## 2. Ownership table

Every mutable object has exactly one owner thread; other threads reach it
only through the listed facade. "Loop" means the asyncio loop thread.

| Object | Owner | Facade for others | Notes |
|---|---|---|---|
| `Transport`, `Decoder`, acquisition channel sender | `sadi-acq` (Rust) | `AcqHandle` (PyO3): `recv_block`, `send_command`, `metrics`, `stop`, `join` | Rust `Mutex` inside `AcqHandle` guards only the receiver and the command sender; the thread itself holds no Python object. |
| Acquisition channel receiver | `sadi-pipeline` | none | Exactly one consumer. |
| `WalWriter`, segment fd, lock fd | `sadi-wal-writer` | `WriterHandle` (DS 7.3) | `WriterHandle._lock` is a leaf lock. |
| Pending map (seq -> RawBlock awaiting durability) | `sadi-pipeline` | none | Plain dict, single thread. |
| Streaming analysis state (settle, slip, tare) | `sadi-pipeline` | events posted to loop | Pure functions of the durable stream. |
| Display queue | loop (`asyncio.Queue`) | `loop.call_soon_threadsafe` from the pipeline | Section 3.4. |
| `JobManager` registry, per-key current job, result versions | loop | `JobManager.submit/cancel` are plain methods callable only on the loop; threads post via `call_soon_threadsafe` | No lock: single-threaded by construction. Calling them from another thread is a programmer bug and asserts `threading.current_thread() is loop_thread`. |
| Worker command pipe (parent end) | loop | `WorkerSlot.send` | `Connection.send` on a small message does not block the loop measurably; the pipe is never allowed to fill (one outstanding command per slot). |
| Worker event pipe (parent end) | `sadi-job-pump-<n>` | posts `JobEvent` to loop | Blocking `recv()` off the loop. |
| `ResultsBroadcaster` latest-per-key map, WebSocket set | loop | none | Section 9. |
| `SessionHandle` lifecycle state (`OPEN`, `STOPPING`, `CLOSED`) | loop | `SessionHandle.state` read-only property | Only the loop transitions it; section 11. |
| Metrics snapshots | each producer | immutable pydantic snapshot swapped atomically | Readers never see a half-updated struct. |

## 3. Queues, bounds and backpressure

### 3.1 The WAL path never drops

The WAL path is: device -> `sadi-acq` -> acquisition channel ->
`sadi-pipeline` -> `WriterHandle.submit` -> writer queue -> disk. Rule,
tested by R8 acceptance 1, DS8 and J5:

> No stage on the WAL path drops, coalesces, reorders or times out a
> RawBlock. When a stage cannot make progress it blocks, counts the wait,
> and after `STALL_TIMEOUT_S = 5` s declares a stall (DS 6.4) which stops
> acquisition loudly. Bytes can then only be lost by the device's own FIFO,
> which the device reports and which is recorded as `RAW_JUNK(reason=3)`.

Derived paths (display frames, progress events) may coalesce; section 3.4
and 8 say exactly how.

### 3.2 Queue table

| Queue | From -> To | Type | Bound | On full | Constant |
|---|---|---|---|---|---|
| acquisition channel | `sadi-acq` -> `sadi-pipeline` | Rust `crossbeam_channel::bounded` of `RawBlock` | 256 blocks (about 12 s at 50 packets per block) | sender blocks; `channel_full_waits += 1`; after 5 s `AcqEvent::ConsumerStalled` is emitted and the thread keeps blocking (never drops) | `ACQ_CHANNEL_BLOCKS` |
| command channel | loop/pipeline -> `sadi-acq` | Rust `crossbeam_channel::bounded` of `AcqCommand` | 16 | `send_command` returns `Err(AcqError::CommandQueueFull)`; a programmer bug, since at most one command is in flight | `ACQ_COMMAND_DEPTH` |
| writer queue | `sadi-pipeline`, loop -> `sadi-wal-writer` | `queue.Queue` | 64 MiB / 65536 items (DS 7.1) | `submit` blocks up to 2 s then `Err(Backpressure)`; pipeline treats it as a stall | DS constants |
| pending map | pipeline internal | dict | implicitly bounded by the writer queue | n/a | n/a |
| display queue | `sadi-pipeline` -> loop | `asyncio.Queue[TraceFrame]` | 64 frames | pipeline merges the new frame into the newest queued frame (downsample), `display_frames_coalesced += 1`; never blocks | `DISPLAY_QUEUE_FRAMES` |
| analysis events | `sadi-pipeline` -> loop | `call_soon_threadsafe` callbacks | unbounded (loop callback list) | n/a: rate is bounded by points and markers (tens per minute) | n/a |
| job commands | loop -> worker | `multiprocessing.Pipe` | one outstanding command per slot | `WorkerSlot.send` refuses a second in-flight command (`JobError.SlotBusy`); the manager queues in its own list | n/a |
| job events | worker -> pump -> loop | `multiprocessing.Pipe` then `call_soon_threadsafe` | pipe buffer; progress rate-limited at the source (100 ms) and coalesced by the pump | pump keeps only the newest `Progress` per job while the loop is behind; terminal events are never coalesced | `PROGRESS_MIN_INTERVAL_MS` |
| analytic requests | loop -> `sadi-analytic` | executor | 1 running + 1 pending | a newer request replaces the pending one (latest wins) | n/a |
| results fan-out | loop -> WebSocket clients | per-client `asyncio.Queue[bytes]` | 256 messages | slow client: queue drained to the latest envelope per key, `client_coalesced += 1`; after 10 s without progress the socket is closed with code 1008 and a log line | `WS_CLIENT_QUEUE` |

### 3.3 RawBlock grouping (R8)

`sadi-acq` closes a block when it holds `ACQ_BLOCK_MAX_PACKETS = 50`
packets or `ACQ_BLOCK_MAX_MS = 50` ms have passed since the first packet,
whichever comes first, or when a non-data packet (type 2 or 4) or a junk run
is encountered (so block boundaries carry meaning). A block is never split
across channel sends and never merged after it is closed. The `RawBlock`
carries exactly the fields of the DS 3.4 payload plus the list of junk runs
that preceded it (DS 3.5), so the pipeline can submit `RAW_JUNK` then
`RAW_BLOCK` without reinterpreting bytes.

### 3.4 Display gate and coalescing

The pipeline loop (one iteration):

1. `block = acq.recv_block(timeout_ms=20)` with the GIL released. On
   `None` (timeout) go to step 4.
2. For each junk run: `writer.submit(RAW_JUNK)`. Then
   `seq = writer.submit(RAW_BLOCK)`; on `Err(Backpressure)` enter stall
   handling (DS 6.4). Put `(seq, block)` in the pending map.
3. Repeat 1-2 while the channel is non-empty (`acq.try_recv_block()`), up
   to 64 blocks, so a burst is submitted as one writer batch.
4. `d = writer.metrics().durable_seq`. Pop every pending entry with
   `seq <= d` in seq order; for each: decode, run the streaming stage,
   build a `TraceFrame(enqueued_seq, durable_seq, samples...)`, post to the
   display queue (coalescing on full), post analysis events.
5. If the pending map is non-empty and the channel is empty,
   `writer.wait_durable(oldest_pending_seq, timeout_s=0.02)` instead of a
   bare recv timeout, so the gate reacts within one group commit.
6. Update `PipelineMetrics`.

The display path is the only place in the system that coalesces, and it
sits strictly downstream of durability, so coalescing a trace frame loses
nothing that is not already on disk (DS I7).

### 3.5 Stall handling

On `Err(Backpressure)` from `submit`, on `durable_seq` making no progress
for `STALL_TIMEOUT_S` while pending is non-empty, or on
`AcqEvent::ConsumerStalled`: the pipeline posts `PipelineEvent.Stalled` to
the loop; the loop sends `AcqCommand::Stop`, enqueues the
`MARKER(acquisition_stopped, reason=store_stalled)` (DS 6.4), transitions
the session to `STOPPING_STALLED` and surfaces `StoreError.Stalled`. The
pipeline keeps its pending map and keeps retrying `submit` of the held
blocks in order; nothing is discarded. When the writer recovers the queue
drains and the UI shows "ALL DATA SAVED" again before the user may resume.

## 4. The GIL and the Rust boundary

- `sadi-acq` is a `std::thread` started from `AcqHandle::start`; it never
  touches a Python object, so it never needs the GIL. All Python-visible
  state is behind the channel endpoints in `AcqHandle`.
- `AcqHandle.recv_block(timeout_ms)` and `AcqHandle.join()` wrap the
  blocking call in `py.allow_threads(|| ...)`. The writer thread and the
  loop therefore run while the pipeline waits.
- `AcqHandle.send_command(cmd)` is non-blocking (`try_send`). Replies to
  commands (`StopAck`, `Version`, `Boot`) arrive as `AcqEvent` items on
  the same channel as blocks, in stream order, so Python sees exactly the
  device's ordering. This makes the Rust thread the single owner of the
  `Transport` (it is `&mut self`), and the session state machine
  (`crates/sadi-proto/src/session.rs`, ~SB1MWFD) runs on that thread, fed
  by the command channel and the decoder output.
- Stop: `AcqHandle.stop()` sends `AcqCommand::Shutdown`; the thread sends
  the device `Stop`, waits up to `ACQ_STOP_ACK_TIMEOUT_MS = 500` for the
  stop-ack (framing whatever arrives as blocks), flushes its partial block
  as a final `RawBlock` (junk reason 4, "truncated by Stop", if a packet
  was cut), then exits. The channel is left intact for the pipeline to
  drain; dropping the sender is what lets `recv_block` return `Closed`
  after the last item.
- The writer thread is pure Python and holds the GIL only when not inside
  `os.write`/`os.fsync` (CPython releases it there). Its CRC work is a C
  extension that also releases the GIL for payloads above a few kB.
- The pipeline's decode is numpy on a 30 kB block; GIL contention with the
  loop is measured by `PipelineMetrics.gate_lag_ms`; the budget is one
  group commit (DS 6.6).

## 5. Metrics

Each is a frozen pydantic snapshot, swapped atomically by its owner, read
by `/api/metrics` and the status bar. Every field that measures waiting is
a backpressure signal and is logged at WARNING when it first exceeds its
threshold and at INFO when it recovers.

| Snapshot | Owner | Fields |
|---|---|---|
| `AcqMetrics` (R8) | `sadi-acq` | `channel_depth`, `channel_high_water`, `blocks_sent`, `packets_read`, `bytes_read`, `junk_runs`, `junk_bytes`, `msgcount_gaps`, `channel_full_waits`, `channel_full_wait_ms_total`, `last_read_mono_ns`, `state` (`IDLE`, `STREAMING`, `STOPPING`, `STOPPED`, `FAILED`), `error` |
| `WriterMetrics` | `sadi-wal-writer` | DS 7.2 verbatim |
| `PipelineMetrics` (B3) | `sadi-pipeline` | `pending_blocks`, `pending_bytes`, `enqueued_seq`, `displayed_seq`, `gate_lag_ms` (last, p50, p99 over 256), `stage_ms` (same ring), `display_frames_posted`, `display_frames_coalesced`, `stalls`, `state` (`RUNNING`, `STALLED`, `DRAINING`, `STOPPED`) |
| `JobMetrics` (J1) | loop | `queued`, `running`, `superseded_total`, `cancelled_total`, `killed_total`, `failed_total`, `done_total`, `worker_restarts`, `progress_events`, `progress_coalesced`, `queue_wait_ms` (ring), `run_ms` (ring), per slot `{state, job_id, key, pid}` |
| `ResultsMetrics` (J4) | loop | `clients`, `envelopes_sent`, `client_coalesced`, `clients_dropped`, per key `{data_version, result_version, state}` |

Thresholds: `gate_lag_ms > DISPLAY_LAG_WARN_MS (250)`, `channel_depth >
ACQ_CHANNEL_BLOCKS / 2`, `queue_wait_ms p50 > 1000`, any
`*_coalesced` increment on the results fan-out.

## 6. Job lifecycle state machine

A job is one unit of CPU work keyed by `JobKey` and bound to a
`data_version` (section 9.1). States:

```
                 submit(key)                dispatch to free slot
  (new) ------------------------> QUEUED -----------------------> RUNNING
                                    |                                |
                                    | newer submit(key)              | first Progress event
                                    v                                v
                                SUPERSEDED                      PROGRESSING
                                                                 |   |   |   |
                     Done event ---------------------------------+   |   |   |
                     Failed event / worker crash --------------------+   |   |
                     cancel(job_id) acknowledged or killed ---------------+   |
                     newer submit(key): cancel + replace ----------------------+
                                  |          |          |          |
                                  v          v          v          v
                                DONE      FAILED    CANCELLED  SUPERSEDED
```

| From | Event | To | Side effects |
|---|---|---|---|
| QUEUED | slot free, highest priority | RUNNING | `WorkerSlot.send(JobSpec)`; `queue_wait_ms` sampled |
| QUEUED | `submit(same key)` | SUPERSEDED | removed from queue, never sent; `superseded_total += 1` |
| QUEUED | `cancel` | CANCELLED | removed from queue |
| RUNNING | `Progress` | PROGRESSING | first progress stored |
| RUNNING or PROGRESSING | `Done(result)` | DONE | result forwarded to `ResultsBroadcaster` if the job is still the current job for its key, else discarded with a DEBUG log |
| RUNNING or PROGRESSING | `Failed(error)` | FAILED | typed `JobError` forwarded; a worker crash (pipe EOF, exit code) is `JobError.WorkerCrashed(pid, exit_code)`; slot restarted |
| RUNNING or PROGRESSING | `cancel` | CANCELLED (after ack or kill) | section 7.2 |
| RUNNING or PROGRESSING | `submit(same key)` | SUPERSEDED (after ack or kill) | section 7.1; new job is QUEUED immediately and dispatched as soon as any slot is free, not necessarily the one being vacated |
| any terminal | anything | (ignored) | late events from a terminal job are counted in `late_events` and dropped |

Terminal states are DONE, FAILED, CANCELLED, SUPERSEDED. Every transition
is logged at INFO with `job_id`, `key`, `data_version`, from, to, and the
elapsed time in the previous state; FAILED at ERROR.

`JobSpec` (frozen pydantic): `job_id: UUID`, `key: JobKey`, `data_version:
int`, `task: str` (registry name, never a pickled callable: workers import
the task by name so a stale parent closure cannot be shipped), `inputs:
dict`, `priority: Literal["interactive", "background"]`,
`progress_interval_ms: int = 100`.

## 7. Latest wins: supersede, cancel, kill

### 7.1 Supersede rule

At most one job per key is live (QUEUED, RUNNING or PROGRESSING) at any
instant, plus at most one waiting replacement. `submit(spec)`:

1. If a QUEUED job has the same key: mark it SUPERSEDED, drop it from the
   queue.
2. If a RUNNING or PROGRESSING job has the same key: set its outcome to
   `superseded`, send `Cancel(job_id)` on the slot's command pipe, start
   the grace timer (7.2). It stays in its state until the worker's
   `Cancelled` ack or the kill, then becomes SUPERSEDED.
3. Enqueue the new job as QUEUED. It may start on another free slot
   immediately; two jobs with the same key may therefore briefly both be
   on a worker (the old one draining). Their results cannot be confused
   because every event carries `job_id` and the broadcaster accepts only
   the current `job_id` for the key.
4. `ResultsBroadcaster.mark_stale(key, new data_version)` (section 9.3).

A result from a superseded or cancelled job is discarded on arrival,
always, even if it is "final": a value computed for an older data version
must never overwrite a newer analytic value.

### 7.2 Cancellation points and hard kill

Cooperative first, then forced:

- The worker runs the task with a `CancelToken`. `token.check()` returns
  `True` once a `Cancel` for the running `job_id` has arrived on the
  command pipe (the watchdog thread sets a `threading.Event`). Tasks must
  call `token.check()` at every cancellation point: at least once per
  `progress_interval_ms`, between MC batches, between refit
  iterations, before and after every numpy call that is expected to take
  more than 50 ms. A task that sees `True` stops, emits `Cancelled`, and
  returns. `token.check()` also throttles and emits the progress event
  (section 8), so a task cannot report progress without also honouring
  cancellation.
- Grace: `CANCEL_GRACE_S = 0.5`. If no `Cancelled` ack arrives within the
  grace, the manager calls `Process.kill()` (SIGKILL / TerminateProcess),
  marks the job CANCELLED or SUPERSEDED with `killed=True`, increments
  `killed_total`, and respawns the slot (`worker_restarts += 1`). The
  respawn is asynchronous; the slot is unavailable until the new worker
  reports `Ready`.
- Killing a worker is always safe because a worker owns nothing durable
  (section 1) and holds only derived state.

### 7.3 Cancel API

`JobManager.cancel(job_id) -> Result[None, JobError]`: `Err(JobError.
Unknown)` if the id is not live; otherwise the 7.2 path with outcome
`cancelled`. `cancel_key(key)` cancels the live job of a key without
submitting a replacement (used when the session stops).

### 7.4 Priority

Two classes. `interactive` (per-point MC interval, refit after an edit)
is dispatched before `background` (full-run bootstrap) and one
slot is reserved for it. Within a class, FIFO by submit time. A background
job is never pre-empted by an interactive one (pre-emption would waste
work and complicate J2's determinism); the reserved slot is the guarantee.

## 8. Progress protocol

Worker -> parent events, all frozen pydantic models serialised with
`model_dump()` over the pipe (no pickled callables or exceptions):

| Event | Fields | Cadence |
|---|---|---|
| `Ready` | `pid`, `slot` | once at worker start |
| `Started` | `job_id` | when the task function is entered |
| `Progress` | `job_id`, `fraction: float 0..1`, `partial: dict or None`, `mono_ns` | at most one per `progress_interval_ms`; `partial` is an intermediate result the UI may show as `refining` (for example the MC interval after N samples) |
| `Done` | `job_id`, `result: dict`, `run_ms` | once |
| `Failed` | `job_id`, `error: JobError` | once |
| `Cancelled` | `job_id` | once, in response to `Cancel` |

Rules:

- `fraction` is monotonic within a job; the pump drops a `Progress` whose
  fraction is lower than the last forwarded one (`progress_coalesced`).
- When the loop is behind, the pump keeps only the newest `Progress` per
  job. `Started`, `Done`, `Failed`, `Cancelled` are never coalesced and
  are delivered in order relative to each other.
- A `partial` is published to the results stream only if the job is still
  current for its key (7.1); otherwise discarded.
- A worker that emits nothing for `WORKER_HEARTBEAT_S = 10` s while
  RUNNING is logged at WARNING once (`JobMetrics.silent_workers`); it is
  not killed, because a legitimately long numpy call cannot check in. The
  hard-kill path is only ever triggered by cancel or supersede.

## 9. Versioned results stream and stale markers

### 9.1 Versions

- `data_version: int` is the WAL `seq` (DS 3.1) of the most recent durable
  record that changes analysis state (`POINT`, `EDIT`, `SETTINGS` with
  scope `analysis`). It is assigned by the store, is identical across
  reconnects and restarts, and ties every number on screen to a verified
  prefix of the WAL (DS I10).
- `result_version: int` is a per-key counter owned by the broadcaster,
  incremented on every envelope it emits for that key. It is process-local
  and restarts at 1 with the process; clients treat a smaller
  `data_version` as older regardless of `result_version`.

### 9.2 Envelope

`ResultEnvelope` (frozen pydantic; J4 owns the wire format in
docs/server/results-stream.md and must keep these fields):

```
protocol_version: 1
key: str                        e.g. "lctt.E", "lctt.yield"
data_version: int
result_version: int
state: "analytic" | "refining" | "final" | "stale"
progress: float                 0..1; 1.0 for final and analytic
job_id: UUID | None
value: dict | None              lab-defined payload (Measured as model_dump)
emitted_ns: int
```

Ordering rule for clients: keep `(data_version, result_version)` per key;
accept an envelope iff its pair is greater than the stored pair; otherwise
drop it and count `client_out_of_order`. Reconnecting clients receive the
latest envelope per key (the broadcaster's map) before any live push.

### 9.3 Sequence after a captured point

Triggered when the pipeline's analysis stage posts `PointCaptured(seq)` to
the loop (seq is durable by construction, section 3.4):

1. `data_version = seq`. The broadcaster re-emits, for every key, the last
   envelope with `state = "stale"` and the new `data_version` (zero
   compute; the UI greys the old numbers immediately).
2. The analytic recompute is scheduled on `sadi-analytic` with
   `data_version`; a pending older request is replaced (latest wins). On
   completion, if `data_version` is still current, one envelope per key
   with `state = "analytic"`, `progress = 1.0`.
3. Refinement jobs are submitted per key (`submit` supersedes the old
   ones, 7.1). Each `Progress` with a `partial` becomes an envelope with
   `state = "refining"` and its `fraction`; `Done` becomes
   `state = "final"`.
4. An envelope for a `data_version` older than the current one is never
   emitted; the check happens on the loop at emit time, so a late analytic
   result and a late job result share one rule.

The user therefore always sees, in order: stale (instant), analytic
(within the recompute, tens of ms), refining (progressive), final. A
number on screen is never older than its marker says.

## 10. Lock order

Locks, from outermost to innermost. A thread acquires only in this order
and never acquires a higher-level lock while holding a lower one. The loop
thread's single-ownership of job and results state means most operations
hold no lock at all.

| Level | Lock | Held by | Protects | May be held while |
|---|---|---|---|---|
| L1 | `SessionHandle._lifecycle` (`threading.Lock`) | loop, pipeline (read) | lifecycle state transitions (section 11) | acquiring L2 or L3 |
| L2 | `AcqHandle` Rust `Mutex` (inside PyO3) | pipeline, loop | channel endpoints | nothing else; released before `recv_timeout` blocks (the receiver is cloned out under the lock) |
| L3 | `WriterHandle._lock` | any producer | seq counter, queue put | nothing: leaf lock (DS 7.3); `queue.put` happens after release when the queue is full, so no thread blocks on the queue while holding the lock |
| L3 | `WriterHandle._durable_cond` (`threading.Condition`) | writer (notify), pipeline (wait) | `durable_seq` watch | leaf; `wait` releases it |
| L3 | metrics swap | each owner | snapshot reference | leaf, a single attribute assignment |

Forbidden, enforced by review and by the J5 lock-order tracer (section
14.3):

- Calling into a Python callback, posting to the loop, or logging a
  handler that may block while holding L1-L3.
- `await` or any blocking call while holding L1.
- Holding any lock across a `multiprocessing.Connection` operation.
- Acquiring any Python lock from the Rust thread (it has none to acquire).

## 11. Shutdown order

Graceful shutdown (user Stop, `SIGINT`/`SIGTERM` once, window close):

1. Loop: `SessionHandle` `OPEN -> STOPPING`. HTTP mutations return 409
   `session_stopping`; reads and the WebSocket keep working so the user
   sees the "SAVING" indicator finish.
2. Loop: `AcqHandle.stop()` (section 4). The Rust thread sends device
   `Stop`, drains the stop-ack, flushes its partial block, drops the
   sender, exits. `AcqHandle.join(timeout_ms=2000)` with the GIL released;
   a timeout is logged at ERROR and the transport is closed from the
   handle (the thread's blocking read then fails with `Closed` and it
   exits). No block already in the channel is affected.
3. Pipeline: `recv_block` returns `Closed` after the last item; the
   pipeline submits every remaining block, enqueues
   `MARKER(acquisition_stopped, reason=user|stop|error)`, then waits until
   `durable_seq >= last submitted seq`, drains the pending map through the
   gate (so the UI gets the last frames), posts `PipelineStopped`, exits.
   The loop joins it with `run_in_executor` so the loop is not blocked.
4. Loop: `JobManager.shutdown()`: every live job is cancelled (7.2), the
   grace runs once for all of them, survivors are killed, `Shutdown` is
   sent to each worker, workers joined with `WORKER_JOIN_S = 2`, then
   killed. Pump threads exit on pipe EOF and are joined. Nothing durable
   is involved, so this step cannot lose data however it ends.
5. Loop (via executor): final snapshot `write_snapshot(state,
   covers_seq = data_version)` (DS 9.1) and `SNAPSHOT_REF` submitted. The
   analytic recompute result for the final `data_version` is awaited
   first so the snapshot carries current state; MC results are not
   waited for (they are regenerable).
6. Loop (via executor): `WriterHandle.close()` (DS 7.3): `DRAINING`,
   `SESSION_CLOSE`, flush, lock release, join. `Err` keeps the process
   alive (DS F23) and the UI shows the Retry / Save elsewhere choice (DS
   6.5).
7. Loop: `ResultsBroadcaster` sends a final `session_closed` control
   frame, closes sockets; uvicorn exits.

The order is fixed by data dependencies: the device must stop before the
channel can end; the channel must end before the pipeline can prove it
submitted everything; jobs must be gone before the snapshot so no late
result mutates state during the write; the snapshot must precede
`SESSION_CLOSE` so the writer is still open for `SNAPSHOT_REF`; the
writer closes last because it is the only thing that makes anything
durable.

Second `SIGINT` while in STOPPING: forced path. Steps 2-4 are skipped or
abandoned; the writer gets `close(timeout_s=0)`: if undurable records
remain it spills them (DS 6.5 step 4) and the process exits with code 3
and an ERROR log naming the spill file. Workers die on pipe EOF.

Writer `FAILED` during shutdown (disk full at the end of a run): step 6
returns `Err`; the session stays in `STOPPING` with the error surfaced;
steps 1-5 are not repeated on Retry, only step 6.

## 12. Kill-mid-write with running jobs

The scenario J5 drives (`kill-during-jobs`, DS 12.2): SIGKILL or
TerminateProcess of the `sadi` process, at a random instant, while the
writer is mid-batch and workers are mid-job; workers are also killed in
random order before, during or after.

What happens, per component, and why no data is at risk:

| Component | At kill | Afterwards | Risk |
|---|---|---|---|
| `sadi-wal-writer` | dies between any two instructions of DS 6.2 | torn tail (DS 5.2, F1); acknowledged prefix intact (I2) | none: the undurable batch was never displayed (I6) |
| `sadi-pipeline` | pending map lost | its blocks were either durable (then also on disk) or never displayed | none |
| `sadi-acq` | dies; the FTDI FIFO keeps filling, the device keeps streaming | at next connect the session layer sends `Stop`, purges, and records the purge as `RAW_JUNK(reason=3)` in the new version | device-side loss only, visible |
| workers | orphaned momentarily | watchdog sees EOF on the command pipe within one `recv`, calls `os._exit(0)`; on POSIX the spawn context additionally makes them children of the dead parent, reaped by init | none: workers hold only derived values and never opened the session dir (asserted by the directory listing diff) |
| worker killed first | pump gets EOF, posts `Failed(WorkerCrashed)` | manager marks FAILED, respawns the slot, and (if the key still has the same `data_version`) resubmits once; a second crash for the same job stays FAILED and is surfaced | none |
| snapshot in flight | tmp file may be left | `.tmp` ignored, old snapshot used (I5) | none |
| results stream | clients see the socket drop | reconnect gets the latest envelope per key from the new process after replay, with `state = "analytic"` and the recovered `data_version` | a client may have displayed a `refining` value for a `data_version` that is now ahead of the recovered prefix only if that record was unacknowledged, which cannot happen (data_version is a durable seq) |

Invariant tested by J5 after every kill, in addition to DS 12.3: the set
of files under the session directory is exactly what the writer and the
snapshot/export writers produce; no worker-created file exists anywhere
under `<data-root>`.

## 13. Deadlock and race analysis

### 13.1 Blocking waits and their release conditions

Every blocking wait in the process, with what unblocks it. A deadlock
requires a cycle; the table shows none exists.

| Waiter | Waits on | Released by | Can the releaser wait on the waiter? |
|---|---|---|---|
| `sadi-acq` | `Transport.read` (timeout) | device bytes or timeout; `Transport.close` from the handle | no: the handle's close takes L2 briefly and never waits for the thread while holding it |
| `sadi-acq` | channel `send` (full) | pipeline `recv` | pipeline waits on writer, writer waits on disk; neither waits on `sadi-acq` |
| `sadi-pipeline` | `recv_block` (timeout) | `sadi-acq` send, or sender drop | no |
| `sadi-pipeline` | `submit` (writer queue full, 2 s cap) | writer batch completion | writer never waits on the pipeline |
| `sadi-pipeline` | `wait_durable` (timeout) | writer `notify_all` after publish | no |
| `sadi-wal-writer` | `queue.get` | any producer | producers never wait on the writer while holding anything the writer needs (L3 is released before a blocking put) |
| `sadi-wal-writer` | `os.write` / `fsync` | kernel | n/a; stall detection (DS 6.4) bounds the user-visible effect |
| `sadi-job-pump-<n>` | pipe `recv` | worker send or EOF | worker never waits on the pump |
| worker | pipe `recv` (idle) | manager `send` | manager never blocks on a worker |
| loop | nothing | n/a | the loop never blocks: joins go through `run_in_executor`, pipes are read by pumps, the Rust thread is joined with the GIL released inside an executor |

The only cycle candidate is pipeline <-> writer: the pipeline blocks in
`submit` while the writer is blocked in `fsync`. That is a wait chain, not
a cycle: the writer does not need anything from the pipeline to finish
the fsync. Its termination is bounded by the 2 s submit cap and the 5 s
stall rule.

### 13.2 Shared-state races

| State | Writers | Readers | Protection | Residual |
|---|---|---|---|---|
| `durable_seq` | writer only | pipeline, loop, UI | published under `_durable_cond`; readers take the snapshot | monotonic, so a stale read is only conservative (displays later, never earlier) |
| seq assignment | any producer | writer | L3 | none |
| pending map | pipeline | pipeline | single thread | none |
| current job per key | loop | loop | single thread | none |
| `data_version` | loop | loop, `sadi-analytic` (by value in the request) | by value | a result tagged with an old version is dropped at emit (9.3 step 4) |
| worker slot state | loop | pumps post, loop mutates | all mutation on the loop | a `Done` arriving after `kill()` is a late event, dropped (section 6) |
| metrics snapshots | each owner | anyone | atomic reference swap | readers may see a snapshot one batch old |
| lifecycle state | loop | pipeline (checks `STOPPING` to decide whether to post frames) | L1 | a frame posted just after `STOPPING` is harmless |
| results per-client queues | loop | loop | single thread | none |

Time-of-check races on the job key (submit while a `Done` is already in
the loop's callback queue) resolve by `job_id` comparison at the point of
effect, never by timing.

### 13.3 Known non-issues, decided

- Two live jobs with one key during supersede (7.1 step 3) is accepted;
  the alternative (wait for the old worker to die before dispatching the
  new job) adds up to `CANCEL_GRACE_S` of latency to every capture.
- Analytic recompute on a thread shares the GIL with the loop; measured
  by `stage_ms`; if the lab's recompute ever exceeds 50 ms it moves to a
  worker under the `interactive` class, which the J1 API already allows.
- `queue.Queue` wakeups use a condition with a timeout in `submit`
  (`SUBMIT_TIMEOUT_S`), so a lost-wakeup bug in the stdlib (none known)
  would surface as `Backpressure`, not a hang.

## 14. Deterministic test strategy (J2, J5)

Principle: every cross-thread hand-off in sections 1-3 and 6-9 goes
through an injectable abstraction, so tests run the whole model on one
thread with a scripted interleaving and a fake clock. No test in J1-J5
sleeps, polls a real clock or depends on OS scheduling.

### 14.1 Seams

| Seam | Production | Test double (J2) |
|---|---|---|
| `Clock` protocol: `monotonic_ns()`, `sleep(s)`, `deadline(s)` | `time.monotonic_ns`, real sleep | `FakeClock.advance(ns)`; `sleep` records and returns |
| `Executor` protocol for the pool: `spawn_slot()`, `send(slot, cmd)`, events via callback | `multiprocessing` spawn + pumps | `InlineExecutor`: runs the task function in-process on `step()`, yielding at every `token.check()` so the test chooses when progress, cancel or supersede land |
| `Scheduler`: the manager's "dispatch when a slot is free" hook | loop callbacks | `ControllableScheduler.step(n)` and `run_until_idle()` |
| `LoopPoster`: `call_soon_threadsafe` wrapper | asyncio loop | `RecordingPoster` that queues callbacks for `drain()` |
| `BlockSource`: `recv_block`, `try_recv_block` | `AcqHandle` | `ScriptedBlockSource` yielding RawBlocks, timeouts, `Closed` and `AcqEvent`s in a scripted order |
| `WriterHandle` | DS8 | `FakeWriter` with `advance_durable(seq)` under test control so the gate is observable (block submitted, not displayed, then displayed) |
| `TraceSink` | display queue | list |

### 14.2 Interleaving seeds

`Interleaver(seed)` owns the set of runnable actors (pipeline step, writer
publish, scheduler step, worker yield, loop drain) and on each `tick()`
picks one with the seeded RNG. A failure prints the seed and the full
action trace; `Interleaver.replay(trace)` re-executes it exactly. J2's
property tests run `INTERLEAVING_SAMPLES = 500` seeds per scenario;
hypothesis is not used for interleavings because the trace must be a
plain list that J5 can store next to a failing crash artifact.

Mandatory scenarios (J2 recipe, used by J3, J4, J5):

1. Supersede while QUEUED: the old job never starts; one SUPERSEDED, one
   DONE; exactly one `final` envelope, with the new `data_version`.
2. Supersede while PROGRESSING with the old job yielding `partial` after
   the supersede: the partial is discarded; no envelope with the old
   `data_version` after the stale marker.
3. Cancel never acknowledged: fake clock advances past `CANCEL_GRACE_S`;
   kill is invoked once; slot restarted; state CANCELLED with
   `killed=True`.
4. Worker crash mid-job: FAILED, one resubmit, then FAILED surfaced on
   second crash.
5. Gate: three blocks submitted, `advance_durable(2)`: exactly two frames
   displayed, `pending_blocks == 1`.
6. Stall: `FakeWriter` returns `Backpressure`; pipeline posts `Stalled`;
   blocks retained; after `advance_durable` everything is displayed in
   order with no gap.
7. Shutdown order 11.1-11.7 as a recorded action trace compared against
   the golden order; a `FAILED` writer at step 6 keeps the session in
   STOPPING.
8. Client ordering: envelopes delivered out of order to a
   `ResultsClient` model are dropped per 9.2.

### 14.3 Real-concurrency checks (J5)

Deterministic tests prove the logic; J5 adds the real threads and
processes:

- Lock-order tracer: a `sys.setprofile`-free approach is used because
  profiling hooks are too slow at 1000 packets/s. Instead every lock in
  section 10 is a `TracedLock(level, name)` wrapper in test builds; it
  records `(thread, level, acquire/release)` and asserts on acquire that
  the thread holds no lock of a lower or equal level. Production uses the
  same class with recording compiled out by a module flag.
- Soak: simulator at full rate, slow consumer (`sleep:300` fsync
  failpoint), 60 s; asserts no drop on the WAL path (every msgCount
  present or marked as junk), `channel_full_waits > 0`, no gate violation
  (`displayed_seq <= durable_seq` sampled every frame).
- `kill-during-jobs` (section 12) on all three OS in the DS6 harness, at
  least 50 iterations per OS, workers killed in random order.
- Thread sanitizer equivalents are not available for CPython; instead the
  soak runs with `PYTHONDEVMODE=1` and `faulthandler` enabled, and a
  watchdog thread dumps all stacks if the gate or the loop makes no
  progress for 10 s (that is the deadlock detector).

## 15. Module map and public signatures

```
python/sadi/jobs/              (J1)
    state.py      JobState, JobSpec, JobEvent*, JobError, JobKey
    manager.py    JobManager(submit, cancel, cancel_key, shutdown, metrics)
    pool.py       WorkerSlot, worker_main, CancelToken
python/sadi/jobs/testing/      (J2)
    clock.py      Clock, FakeClock
    executor.py   InlineExecutor, ControllableScheduler, Interleaver
python/sadi/core/pipeline.py   (B3)  Pipeline, PipelineMetrics, TraceFrame
python/sadi/server/results.py  (J4)  ResultEnvelope, ResultsBroadcaster
crates/sadi-py/src/acq.rs      (R8)  AcqHandle, AcqCommand, AcqEvent, RawBlock, AcqMetrics
```

Signatures the implementing tickets must match (typani `Result`):

```
# sadi.jobs.manager
class JobManager:
    def submit(self, spec: JobSpec) -> Result[JobId, JobError]
    def cancel(self, job_id: JobId) -> Result[None, JobError]
    def cancel_key(self, key: JobKey) -> Result[None, JobError]
    async def shutdown(self, grace_s: float = CANCEL_GRACE_S) -> Result[None, JobError]
    def metrics(self) -> JobMetrics

# sadi.jobs.pool
class CancelToken:
    def check(self, fraction: float, partial: dict | None = None) -> bool

# sadi.core.pipeline
class Pipeline:
    def start(self) -> Result[None, PipelineError]
    def stop(self, reason: StopReason) -> Result[None, PipelineError]   # non-blocking request
    def metrics(self) -> PipelineMetrics

# sadi.server.results
class ResultsBroadcaster:
    def mark_stale(self, data_version: int) -> None
    def publish(self, envelope: ResultEnvelope) -> Result[None, ResultsError]
    def latest(self) -> dict[str, ResultEnvelope]

# sadi_py (PyO3)
class AcqHandle:
    def recv_block(self, timeout_ms: int) -> RawBlock | AcqEvent | None   # GIL released
    def try_recv_block(self) -> RawBlock | AcqEvent | None
    def send_command(self, cmd: AcqCommand) -> None                      # raises AcqError.CommandQueueFull
    def metrics(self) -> AcqMetrics
    def stop(self) -> None
    def join(self, timeout_ms: int) -> bool                              # GIL released
```

Error taxonomy additions (frozen pydantic, `hint` for the UI): `JobError`:
`Unknown(job_id)`, `WorkerCrashed(pid, exit_code)`, `TaskFailed(task,
repr)`, `SlotBusy(slot)`, `ShuttingDown`. `PipelineError`: `Stalled`,
`Store(StoreError)`, `Acq(AcqError)`. `ResultsError`: `StaleVersion(key,
data_version, current)`.

Constants (one module, `sadi/core/limits.py`, so B3, J1, J4 and R8 share
them; R8 mirrors the Rust-side ones in `acq.rs` and a test compares the
two): `ACQ_CHANNEL_BLOCKS = 256`, `ACQ_COMMAND_DEPTH = 16`,
`ACQ_BLOCK_MAX_PACKETS = 50`, `ACQ_BLOCK_MAX_MS = 50`,
`ACQ_STOP_ACK_TIMEOUT_MS = 500`, `DISPLAY_QUEUE_FRAMES = 64`,
`WS_CLIENT_QUEUE = 256`, `WORKER_COUNT` (computed), `CANCEL_GRACE_S =
0.5`, `WORKER_JOIN_S = 2`, `WORKER_HEARTBEAT_S = 10`,
`PROGRESS_MIN_INTERVAL_MS = 100`, `INTERLEAVING_SAMPLES = 500`.
`STALL_TIMEOUT_S`, `DISPLAY_LAG_WARN_MS`, `SUBMIT_TIMEOUT_S` are DS
constants and are imported from `sadi.store`.

Logging: module logger via `sadi.logging_setup.get_logger(__name__)`
(Rust: `tracing`); every state transition in sections 6, 11 and 3.5,
every coalescing event, every kill, every backpressure threshold crossing
and every late or out-of-order event is logged. `print` is forbidden.

## 16. Open points

Decided here but needing acknowledgement in the owning docs (filed by the
coordinator; CC1 does not widen its scope for them):

1. docs/data-safety.md 9.1 lists `SESSION_CLOSE` as a snapshot trigger;
   section 11 writes the final snapshot before `SESSION_CLOSE` so that
   `SNAPSHOT_REF` can still be recorded. Recovery does not depend on
   either; DS5 should adopt this order.
2. docs/data-safety.md 7.3 says `WriterHandle.close()` releases the
   session lock; with section 11 that remains true and the snapshot is
   written while the lock is still held (step 5 before step 6).
3. docs/architecture.md shows an `events/` directory; data-safety.md
   stores events in the WAL. This document follows data-safety.md.
4. `docs/device/session.md` (~SB1MWFD) must state that the session state
   machine executes on the acquisition thread and is driven by
   `AcqCommand` (section 4); the Rust `session.rs` is still a stub.
5. Whether the streaming analysis stage needs its own thread (section 1)
   is decided by B3's measurement of `stage_ms`; the design allows both
   without changing any interface.

## WebSocket handler is off-loop for hub-locked work (~YNKX6Y1)

`/api/stream` runs every `StreamHub` call that takes the hub lock (`attach`,
`hello`, `poll`, `next_seq`, `detach`) via `asyncio.to_thread`, so a writer or
snapshot holding the lock stalls only that handler, never the event loop or
other clients. `poll` is serialised by a separate `_poll_lock` so concurrent
off-loop polls cannot reorder events; per-client send order and `seq`
allocation are unchanged, and no frame is dropped. `detach` is shielded so a
cancelled handler still releases its client.
