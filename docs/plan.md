# SADI delivery plan
Status: current

Goal: replace the reference lab VI (32-column CSV) with one portable
local web app (Windows, Linux, macOS). A single `sadi` launcher serves a
React/TypeScript (Vite) UI from a FastAPI backend and opens the browser.
Root epic: ~NFZEVFY. Tickets live in `tickets/` (frob ledger); this file is the map.
Keys below (R1, DS3, ...) are plan-local; `frob ticket show ~HANDLE` for each.

## Architecture in one paragraph

Core shell plus lab modules. The core owns: device (safe Rust `sadi-proto`,
`sadi-py` PyO3 wheel, simulator), session storage and WAL, the uncertainty
engine (`sadi.uncertainty`, decorator `@uncertain`), plotting contracts, the
job system, and the wizard framework. A lab module (`sadi.labs.lctt` is the
first) declares steps, models, analysis and exports through the `LabModule`
contract (PL1). It is a clean boundary, not a general plugin system.

## Non-negotiables

- Data safety: raw samples reach an append-only, checksummed, fsynced WAL
  before they are displayed; sessions are versioned and created O_EXCL, never
  overwritten; snapshots use atomic rename; exports are derived. Crash-kill
  tests on every OS (DS1-DS8, DS6, J5).
- Concurrency: Rust acquisition thread with the GIL released; dedicated WAL
  writer thread (bounded queue, backpressure metrics, never drops); asyncio
  loop does I/O only; CPU work (Monte Carlo, refits) in a cancellable,
  supersedable process pool ("latest wins"); versioned results stream with
  stale markers (CC1, R8, DS8, J1-J5, F16).
- Uncertainty is first class: users and lab authors write plain-math functions;
  `@uncertain` (sympy tracing, full covariance, budget, .symbolic/.latex/
  .partials, numeric and MC fallbacks, units) does the rest (U1-U6).
  Naming: the decorator is `uncertain`, package `sadi.uncertainty`. typani
  already exports `propagate`, `catching`, `Result`, `Ok`, `Err`, `unwrap`;
  none of these may appear in the uncertainty public API, and U6 gates it.
- Settling and creep: always record raw; auto-detect settle (rolling LVDT
  drift slope, threshold, minimum dwell); human confirm key or auto-capture
  with max wait; each point stores window, time-since-load, drift rate and a
  settled/forced-early flag; points re-editable, analysis recomputes from raw.
- Facts: L0 = 0.08313 m is correct for the short sample. the local short-run run is
  slip-contaminated, so it is used only as a slip-detector test case.
- Protocol is unverified: HW1 maps protocol.md section 10 to a hardware
  checklist; HW3 needs the board. v3.41 (R6) is optional.

## Product requirements to ticket map

- Guided run, three phases (LVDT calibration, elastic, plastic), "confidence
  is enough" meter, stop-early advice (user decides): PH1, F12.
- All analysis live, value +/- U with 3 s.f./2 s.f.: A1-A4, SF1, F8, J4, F16.
- Publication-quality plots and one-click PNG/SVG export from the same renderer:
  F3 (renderer), F4 (trace), F5 (calibration + residuals), F6 (stress-strain,
  E fit, 0.2% offset yield), F7 (creep), F15 (export screen).
- UI/UX: F0 (docs/ux.md, Fable, wireframes, usability protocol), F0B (live
  view, Fable), F9 (wizard shell), F11-F13, F14 (usability pass).
- Many labs: PL1, WIZ1, TS1 (LCTT module).
- Uncertainty budget panel and formula rendering: U4, F17.

## Workstreams (epics)

### ~JCC7HDM Docs, architecture and cross-OS CI/packaging

| Key | Id | Title | Points | Model | Blocked by |
|---|---|---|---|---|---|
| D0 | ~1DQHSR7 | Architecture doc, repo layout and docs index | 3 | Sonnet |  |
| C1 | ~M7BT5SB | CI matrix: Windows, Linux, macOS (Rust, Python, web) | 5 | Sonnet | R1, P1, F1 |
| C2 | ~JX9JXZ4 | Wheels and release workflow with install smoke test (maturin, 3 OS) | 5 | Sonnet | R7, PK1, L1 |
| PORT1 | ~PVJNZ7V | Portability audit: serial ports, drivers, udev, paths, line endings | 3 | Sonnet | R5 |
| DOC1 | ~JS6PJJY | User guide: running a test with the app (procedure, two specimens, creep) | 3 | Sonnet | F12, F8, L1, TS1 |

### ~EEDYF4K Device layer: sadi-proto, simulator, serialport backend, sadi-py

| Key | Id | Title | Points | Model | Blocked by |
|---|---|---|---|---|---|
| R1 | ~M197V9E | Rust workspace scaffold, error types, Transport trait, module stubs | 3 | Sonnet |  |
| R2 | ~80SB0TA | sadi-proto codec: v1.003 commands, packets, ADC scaling, resync decoder | 8 | Sonnet | R1 |
| R3 | ~SB1MWFD | sadi-proto session: connect/query/reset/start/stop state machine with retries | 5 | Sonnet | R1, R2 |
| R4A | ~CSWAMV8 | Simulator device: protocol-faithful SADI v1.003 Transport | 8 | Sonnet | R1, R2 |
| R4B | ~8XCPH41 | Simulator physics and signal faults: wire, LVDT, noise, drift, creep, slip, saturation | 8 | Sonnet | R1 |
| R4C | ~ZCE4AHC | Simulator byte-level faults: dropped, duplicated, corrupted, truncated bytes | 3 | Sonnet | R1 |
| R5 | ~Q4YBED4 | serialport backend over the FTDI VCP (Transport impl) | 5 | Sonnet | R1 |
| R6 | ~2GGPZ5K | Optional: v3.41 codec (CRC-16/CCITT-FALSE framing) | 5 | Sonnet | R1 |
| R7 | ~QTAS277 | sadi-py: PyO3/maturin core bindings (Session, devices, numpy blocks) | 8 | Sonnet | R3, R4A, R5 |
| R7B | ~JBD8YVD | sadi-py: simulator and fault-plan bindings | 3 | Sonnet | R7, R4B, R4C |
| HW1 | ~F4KKZCS | Hardware-verification checklist mapped to protocol.md section 10 | 3 | Sonnet |  |
| HW2 | ~X42K86Y | hwprobe tool: scripted probe, raw capture and replay Transport | 5 | Sonnet | R3, R5, HW1 |
| HW3 | ~CTSXSRE | Run hardware session and fold findings back (needs the physical board) | 5 | Sonnet | HW2, R2 |

### ~EY2JADK Data safety: WAL, sessions, snapshots, crash recovery

| Key | Id | Title | Points | Model | Blocked by |
|---|---|---|---|---|---|
| DS1 | ~CKTER59 | Data-safety design: WAL format, sessions, snapshots, per-OS durability, recovery | 8 | Fable | D0 |
| DS2 | ~JA5DMTN | store/durable: cross-OS fsync, dir-fsync, atomic replace, exclusive create | 5 | Sonnet | P1, DS1 |
| DS3 | ~4668M06 | store/wal: append-only checksummed fsynced writer, reader, recovery | 8 | Sonnet | DS1, DS2 |
| DS4 | ~GCJAR1J | store/session: versioned O_EXCL session dirs, manifest, lock, resume | 5 | Sonnet | DS1, DS2 |
| DS5 | ~K6BT3MG | store/events+snapshot: point/edit event log, atomic snapshots, replay | 5 | Sonnet | DS3, DS4, P2 |
| DS6 | ~HAH4MTB | Crash-recovery tests: kill the process mid-write on every OS | 8 | Sonnet | DS3, DS4, DS5 |
| DS7 | ~36JQFXT | store/exports: derived exports with provenance, tmp + rename | 3 | Sonnet | DS4, DS5 |

### ~CV3NWW5 Python analysis: calibration, uncertainty, settle, creep, slip, export

| Key | Id | Title | Points | Model | Blocked by |
|---|---|---|---|---|---|
| P1 | ~XDK2EVN | Python scaffold: uv project, ruff, typani lint, pytest, core/ and labs/ layout | 3 | Sonnet |  |
| P2 | ~FY28A3R | core models: pydantic domain models and error taxonomy | 5 | Sonnet | P1, D0 |
| PL1 | ~CYC6ZT7 | Lab-module boundary: core shell vs lab plugin contract (LabModule protocol) | 5 | Sonnet | P2 |
| WIZ1 | ~XP2D6HY | Wizard framework: step state machine, undo/redo command log, step rail data | 5 | Sonnet | PL1, DS5 |
| SF1 | ~M27Y4NY | Significant-figure and confidence-readout formatter (class rule) | 3 | Sonnet | P2 |
| A1 | ~NQKWT3Y | LCTT calibration: LINEST-equivalent fit with standard errors and t95 | 5 | Sonnet | P2, U1, U2 |
| A2 | ~9TZ8D2S | LCTT tare and strain/stress/load with RSS uncertainty | 5 | Sonnet | A1, U2 |
| A3 | ~TQ7ZKZW | LCTT E fit (selectable window), r^2, secant E, yield, saturation warning | 8 | Sonnet | A2, U2, U4 |
| A4 | ~19WDD6Q | Live recompute engine: update all results after every captured point | 5 | Sonnet | A1, A2, A3, SF1, DS5 |
| X1 | ~7P8582F | CSV export in the 32-column LabVIEW schema | 5 | Sonnet | A4, DS7 |
| S1 | ~7Q9BX19 | Settle detector: rolling LVDT drift slope, threshold and minimum dwell | 5 | Sonnet | P2, R4B |
| S2 | ~QPQKQEK | Capture modes: human confirm key, auto-capture with max wait, forced-early | 3 | Sonnet | S1, DS5 |
| CR1 | ~7NDJSG8 | Creep fit: strain vs log-time per hold | 5 | Sonnet | P2, R4B, U1 |
| CR2 | ~T3M5GJG | Slip detector: sudden strain steps without load change | 5 | Sonnet | CR1, R4B |
| CR3 | ~DQ1C3W6 | Pre-test clamp-slip check procedure | 3 | Sonnet | CR2 |
| TS1 | ~XMK16Q2 | Two-specimen workflow: long (elastic) and short (plastic) sample runs | 5 | Sonnet | PL1, WIZ1, A4, S2 |

### Planning: guided-run guidance


| Key | Id | Title | Points | Model | Blocked by |
|---|---|---|---|---|---|
| PH1 | ~G2YNMJB | Guided run engine: phase-wise next-step guidance and confidence status | 5 | Sonnet | A4, TS1 |

### ~WEDCSRM Backend: FastAPI server, acquisition pipeline, WebSocket, launcher

| Key | Id | Title | Points | Model | Blocked by |
|---|---|---|---|---|---|
| B2 | ~GX511CP | Device service: sadi_py wrapper returning typani Results, reconnect, sim/real select | 5 | Sonnet | R7, P2 |
| B3 | ~60ZNFTD | Acquisition pipeline: raw -> WAL (durable) -> analysis -> display | 8 | Sonnet | B2, DS3, DS4, S1, DS8, J1 |
| B4 | ~X3H80G2 | FastAPI app: REST endpoints (sessions, points, results, export) | 8 | Sonnet | P2, PL1, WIZ1, B3, A4, PH1 |
| B5 | ~4QRM2GS | Binary WebSocket stream: trace frames, state and result push | 5 | Sonnet | B3, B4 |
| L1 | ~0VYJVFZ | `sadi` launcher: serve UI + API, pick port, open browser, flags | 3 | Sonnet | B4, B5 |
| PK1 | ~ZKJSYXC | Packaging: bundle built UI into the sadi wheel, entry points | 3 | Sonnet | F1, L1 |

### ~J21Z778 Frontend: React/TypeScript live view and workflow

| Key | Id | Title | Points | Model | Blocked by |
|---|---|---|---|---|---|
| F0 | ~GKVPN2E | UX design doc: wizard flow, step rail, wireframes (ASCII), keyboard map | 8 | Fable | D0, PL1 |
| F0B | ~KR3SSE1 | Live-view UX design: readouts, trace, indicators, stress-strain, guidance placement | 5 | Fable | F0 |
| F1 | ~21F3H53 | Web scaffold: Vite + React + TypeScript, lint, vitest, API client | 3 | Sonnet |  |
| F3 | ~MQYWW87 | Plot renderer core: publication-quality canvas, annotations, one-click PNG/SVG export | 8 | Sonnet | F1, F0B |
| F4 | ~7KWS2S7 | Live trace plot: scrolling binary-WebSocket trace with settle markers | 5 | Sonnet | F3, B5 |
| F5 | ~DDAPA9P | Calibration plot: fit with CI band, equation annotation and residuals | 3 | Sonnet | F3, A1 |
| F6 | ~3MJNBZY | Stress-strain plot: live E fit, selectable window, 0.2% offset yield | 5 | Sonnet | F3, A3 |
| F7 | ~7WJVKMW | Creep plot: strain vs log-time per hold with fit and slip markers | 3 | Sonnet | F3, CR2 |
| F8 | ~9PMPWH8 | Results panel: best value +/- U, 95% interval, plain-language confidence | 5 | Sonnet | F1, A4, F0 |
| F9 | ~2ZQVKAB | Wizard shell: step rail, next-action panel, status bar, keyboard capture | 8 | Sonnet | F1, F0, WIZ1, B4 |
| F11 | ~74FQXWT | Run screens: calibrate, tare, elastic, plastic capture screens with live view | 8 | Sonnet | F9, F4, F5, F6, F7, F8, F12, F16 |
| F12 | ~9EFDXQE | Guidance UI: next-step panel, confidence meter, stop-early recommendation | 5 | Sonnet | F9, PH1, F0B |
| F13 | ~FHNEDX8 | Review screen: re-edit points, window edits, undo/redo, results recompute | 5 | Sonnet | F9, F6, F8 |
| F14 | ~W5XJBZT | Usability pass: scripted walkthrough, issue log and fixes | 5 | Sonnet | F11, F13, T2, F17 |
| F15 | ~H8WGMBV | Results/Export screen: report view, figure export, CSV download | 3 | Sonnet | F9, F3, X1, F8 |
| F16 | ~4XEGRNJ | Results-stream client: version/stale marker and refinement progress in the UI | 3 | Sonnet | F1, J4, F8 |
| F17 | ~61M215J | Uncertainty budget and formula panel: dominant input, rendered LaTeX derivation | 5 | Sonnet | F8, U4, B4 |

### ~GX8YEZ9 Simulator-driven verification with fault injection

| Key | Id | Title | Points | Model | Blocked by |
|---|---|---|---|---|---|
| T1 | ~WKK27QJ | Backend e2e suite: simulator fault injection (noise, drift, creep, slip, dropped bytes, saturation) | 8 | Sonnet | B5, TS1, CR2, R4C, R7B, DS6, J5, U5 |
| T2 | ~GW7ER11 | Browser e2e (Playwright) on 3 OS: full guided run against the simulator | 5 | Sonnet | L1, F11, F13, F15 |

### ~9QWVY57 Uncertainty engine: sadi.uncertainty (Measured, @uncertain)

| Key | Id | Title | Points | Model | Blocked by |
|---|---|---|---|---|---|
| U1 | ~SP19B1H | sadi.uncertainty core: Measured value type, covariance, units, provenance | 8 | Sonnet | P1 |
| U2 | ~2NVD83Y | @uncertain decorator: sympy tracing, lambdify, full-covariance RSS, .symbolic/.latex/.partials | 8 | Sonnet | U1 |
| U3 | ~FBSDE1R | Fallbacks: numeric-derivative path and Monte Carlo path (method="mc") | 5 | Sonnet | U2 |
| U4 | ~M0XPX0J | Sensitivity coefficients and uncertainty budget (per-input contribution) | 3 | Sonnet | U2 |
| U5 | ~QTA833F | Uncertainty cross-check suite on every lab formula (analytic vs MC vs finite difference) | 5 | Sonnet | U3, U4, A3 |
| U6 | ~66MX8BW | Name-collision check against typani exports (lint/grep gate) | 2 | Sonnet | U1 |

### ~NX209CZ Concurrency: acquisition thread, WAL writer thread, job pool, versioned results stream

| Key | Id | Title | Points | Model | Blocked by |
|---|---|---|---|---|---|
| CC1 | ~DK06Q2F | Concurrency model design: threads, GIL, queues, job lifecycle, versioned results | 8 | Fable | D0, DS1 |
| R8 | ~A8Y67RG | sadi-py acquisition thread: GIL-released reader with bounded channel | 5 | Sonnet | R7, CC1 |
| DS8 | ~3F2W55E | WAL writer thread: bounded queue, backpressure metrics, fsync off the acquisition path | 5 | Sonnet | DS3, CC1 |
| J1 | ~V9NMTHC | Job system core: lifecycle state machine, process pool, cancel and supersede (latest wins) | 8 | Sonnet | P2, CC1 |
| J2 | ~VAX9DG6 | Deterministic job test harness: fake clock, controllable scheduler, inline executor | 5 | Sonnet | J1 |
| J3 | ~PX6X3ZQ | Progressive background jobs: Monte Carlo interval refinement | 5 | Sonnet | J2, U3 |
| J4 | ~ETJKV0D | Versioned results stream: instant analytic, progressive refinement, stale markers | 5 | Sonnet | J3, A4, B5 |
| J5 | ~7B4SZGG | Race/deadlock suite incl. kill-mid-write while jobs are running | 8 | Sonnet | J2, J4, DS8, DS6, R8 |

## Dependency graph (levels; a ticket starts when all its blockers are done)

- L1: D0, R1, HW1, P1, F1
- L2: C1, R2, R4B, R4C, R5, R6, DS1, P2, U1
- L3: PORT1, R3, R4A, DS2, PL1, SF1, S1, CR1, U2, U6, CC1 (Fable)
- L4: R7, HW2, DS3, DS4, A1, CR2, F0 (Fable), U3, U4, J1
- L5: R7B, HW3, DS5, A2, CR3, B2, F0B (Fable), R8, DS8, J2
- L6: DS6, DS7, WIZ1, A3, S2, B3, F3
- L7: A4, F5, F6, F7, U5, J3
- L8: X1, TS1, F8
- L9: PH1;  L10: B4;  L11: B5, F9, F17
- L12: L1, F4, F12, F13, F15, J4
- L13: DOC1, PK1, J5, F16;  L14: C2, F11, T1;  L15: T2;  L16: F14

Critical path: R1 -> R2 -> R3 -> R7 -> B2 -> B3 -> B4 -> B5 -> F4/F9 -> F11 -> T2 -> F14,
with the data-safety chain DS1 -> DS2 -> DS3 -> DS4 -> DS5 feeding B3.

## Recommended first parallel batch

Unblocked now: D0 (architecture), R1 (Rust scaffold), P1 (Python scaffold),
F1 (web scaffold), HW1 (hardware checklist). Dispatch these five in parallel
(each owns disjoint paths), then immediately the Fable design tickets that
unblock the most work as their blockers clear: DS1 (data-safety design, after
D0), CC1 (concurrency design, after D0 and DS1), F0 (UX). Second wave once
R1/P1 land: R2, R4B, R4C, R5, P2, U1, C1 (up to ~3 local builders; use goway
for cargo builds).

Serialisation points (single owner, others must lease-widen): `Cargo.toml` and
`lib.rs` files (R1), `python/pyproject.toml` (P1), `web/package.json` (F1),
`crates/sadi-py/tests/**` (R7B then R8, ordered by blocked-by).

## Open questions that block tickets (defaults from docs/open-questions.md)

No question blocks starting work; every ticket proceeds on its default and the
answer only changes a config value.

| Q | Default used | Tickets affected |
|---|---|---|
| Q1 live DAQ vs post-processing | both, plus simulator | B2, X1 |
| Q2 target VI | 32-column reference VI | X1 |
| Q3 E window | manual first/last; auto only a hint | A3, F6 |
| Q4 rate/block | configurable, 50 kS/s, 2500 samples | R4A, B2, S1 |
| Q5 U_V | 2 s of block, SEM optional | A2 |
| Q6 cal heights | only slope matters, intercept = offset | A1 |
| Q8 L0 | 0.08313 m short, 0.5 m long, editable | A2, TS1 |
| Q9 hold/creep/offset yield | hold times, 0.2% offset yield supported | S1, CR1, A3 |
| Q10 LVDT sign | warn plus one-click flip | A2 |
| Q13 rubric | 3 s.f. result, 2 s.f. U, configurable | SF1, F8 |
| Q14 discrepancies (4.8/4.9/5.12 V, 50/42.5 kS/s) | 4.9 V warning, 50 kS/s, configurable | A3, R4A |
| HW-dependent (protocol unverified) | simulator only | HW1-HW3, R5 |

## frob notes

- `frob ticket new` self-commits to `main` (one commit per ticket); the planner
  made no commits of its own. No live cycle was needed to create tickets, but
  `frob work` needs one (`frob cycle new/assign`).
- All scopes were declared with `--new-scope` since no files exist yet.
