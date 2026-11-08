# Results stream

Status: current

Parent: [websocket.md](websocket.md), [api.md](api.md). Code: `sadi.server.results_stream`
(`ResultsStream`). Jobs: [../jobs/jobs.md](../jobs/jobs.md).

Transport-agnostic publisher of versioned results. Each message is a `ResultEnvelope`:

| Field | Meaning |
| --- | --- |
| `protocol_version` | Wire version, currently 1 (`PROTOCOL_VERSION`) |
| `key` | Result name |
| `data_version` | Captured-point generation the value was computed from |
| `result_version` | Per-key counter, strictly increasing in this stream |
| `state` | `analytic`, `refining`, `final` or `stale` |
| `progress` | 0..1 refinement progress (0 for analytic) |
| `value` | Payload; clients never show it without the version and state |

## Flow

- `push_analytic(dv, values)` after each captured point: analytic values go out immediately;
  keys that previously had a result but no new value are re-sent with state `stale`.
- `offer_refinement(env)` takes MC/GP `refining`/`final` envelopes from the job manager.
  Envelopes with `data_version` below the current one are rejected (`StreamErrorCode.STALE_DATA`)
  and never reach clients; non-refinement states give `BAD_STATE`.
- `connect(cb)` replays the latest envelope per key, then live pushes (no history replay).
  A callback that raises is logged and dropped.
