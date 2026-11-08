# SADI architecture

Status: current

Foundation doc. Every workstream cites this file for interfaces. Delivery
map and ticket keys: `docs/plan.md`. Domain facts: `docs/domain.md`.

## Process model

```
browser (React/TS, Vite)
   |  HTTP (REST, problem+json) and binary WebSocket
FastAPI app  (asyncio loop: I/O only)
   |  python calls, typani Result
sadi_py      (PyO3 wheel; acquisition thread runs with the GIL released)
   |  Rust Result -> exception at the PyO3 boundary
sadi-proto   (safe Rust: codec, session state machine)
   |  Transport trait
Transport    (serialport over FTDI VCP | simulator | replay)
```

- One `sadi` launcher process serves the built UI and the API and opens the
  browser. CPU work (Monte Carlo, GP, refits) runs in a cancellable process
  pool ("latest wins"). A dedicated WAL writer thread owns durable writes.
- Raw samples reach the WAL (fsynced) before they are displayed.
- Each layer depends only on the layer directly below it. Lab modules
  (`sadi.labs.*`) plug into the core through the `LabModule` contract.

## Repo layout

| Path | Contents |
|---|---|
| `crates/` | Rust workspace: `sadi-proto` (codec, session, `Transport`), simulator, serialport backend, `sadi-py` (PyO3/maturin) |
| `python/` | uv project: `sadi.core`, `sadi.uncertainty`, `sadi.store`, `sadi.server`, `sadi.labs.lctt`, tests under `python/tests/` |
| `web/` | Vite + React + TypeScript UI, vitest tests |
| `docs/` | All documentation; index in `docs/README.md` |
| `tickets/` | frob ticket ledger |

## Session directory layout

Sessions are versioned, created O_EXCL and never overwritten. Detail and
durability rules are owned by `docs/data-safety.md` and `docs/store/*.md`.

```
<data-root>/sessions/<session-id>/
    manifest.json     format version, specimen, lab module, created-at
    lock              single-writer lock
    wal/              append-only, checksummed, fsynced segments (raw samples)
    events/           point and edit event log
    snapshots/        atomic-rename snapshots (derived, replayable)
    exports/          derived outputs (CSV, figures) with provenance
```

Exports and snapshots are derived: they can always be rebuilt from the WAL
and event log.

## Error-handling convention

1. Rust: every fallible function returns `Result<T, E>` with typed errors in
   `sadi-proto`; no panics on wire or I/O input.
2. PyO3 boundary: `sadi-py` converts a Rust `Err` into a typed Python
   exception (one exception class per error family).
3. Python: the device service catches those exceptions once and returns
   typani `Result[T, E]` with the error taxonomy of `sadi.core.errors`; each
   error carries a user-facing "what to do" hint. Exceptions remain only for
   programmer bugs.
4. HTTP: FastAPI maps `Err` values to RFC 7807 problem JSON (`type`,
   `title`, `status`, `detail`, plus the hint). The UI renders the hint.

Logging: module logger per module, never `print`; log every state change,
boundary crossing, branch and error path.

## Documentation rule

Each change updates the doc that its ticket owns, in the same change. See
`docs/README.md` for the index and the owner table.
