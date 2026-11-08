# SADI documentation index

Status: current

Rule: every change updates the doc it owns in the same change. A ticket
that creates or alters behavior edits its owning doc (table below) in the
same commit; docs are not follow-up work.

Start with `architecture.md` (process model, layout, error convention),
then [plan.md](plan.md) (delivery map).

Pages: [architecture](architecture.md), [domain](domain.md),
[open questions](open-questions.md),
[protocol](protocol.md).

## Existing reference docs

| Doc | Purpose |
|---|---|
| [architecture.md](architecture.md) | Process model, repo layout, session layout, error convention (~1DQHSR7) |
| [concurrency.md](concurrency.md) | Concurrency model: threads, GIL, queues, job lifecycle, versioned results (~DK06Q2F) |
| [concurrency-testing.md](concurrency-testing.md) | Race, deadlock and kill-mid-write test suite (~7B4SZGG) |
| [jobs/jobs.md](jobs/jobs.md) | Job system core: lifecycle, process pool, cancel and supersede (~V9NMTHC) |
| [plan.md](plan.md) | Delivery plan and ticket map |
| [domain.md](domain.md) | LCTT domain facts and formulas |
| [open-questions.md](open-questions.md) | Open questions and confirmed defaults |
| [protocol.md](protocol.md) | SADI wire protocol (section 10: hardware checklist source) |
| [protocol-vectors.json](protocol-vectors.json) | Protocol test vectors |
| [vendor-lib30-reference.txt](vendor-lib30-reference.txt) | Vendor library reference |

## Planned docs and owning tickets

| Doc | Owner | Ticket title |
|---|---|---|
| `docs/ci.md` | ~M7BT5SB | CI matrix: Windows, Linux, macOS (Rust, Python, web) |
| [`docs/concurrency-testing.md`](concurrency-testing.md) | ~7B4SZGG | Race/deadlock suite incl. kill-mid-write while jobs are running |
| [`docs/concurrency.md`](concurrency.md) | ~DK06Q2F | Concurrency model design: threads, GIL, queues, job lifecycle, versioned results |
| `docs/core/device.md` | ~GX511CP | Device service: sadi_py wrapper returning typani Results, reconnect, sim/real select |
| `docs/core/formatting.md` | ~M27Y4NY | Significant-figure and confidence-readout formatter (class rule) |
| `docs/core/lab-modules.md` | ~CYC6ZT7 | Lab-module boundary: core shell vs lab plugin contract (LabModule protocol) |
| [`docs/core/models.md`](core/models.md) | ~FY28A3R | core models: pydantic domain models and error taxonomy |
| `docs/core/pipeline.md` | ~60ZNFTD | Acquisition pipeline: raw -> WAL (durable) -> analysis -> display |
| `docs/core/wizard.md` | ~XP2D6HY | Wizard framework: step state machine, undo/redo command log, step rail data |
| `docs/data-safety.md` | ~CKTER59 | Data-safety design: WAL format, sessions, snapshots, per-OS durability, recovery |
| `docs/device/acquisition-thread.md` | ~A8Y67RG | sadi-py acquisition thread: GIL-released reader with bounded channel |
| `docs/device/codec.md` | ~80SB0TA | sadi-proto codec: v1.003 commands, packets, ADC scaling, resync decoder |
| `docs/device/v3.md` | ~2GGPZ5K | sadi-proto optional v3.41 codec: CRC framing, commands, packets, probe sketch |
| `docs/device/serial.md` | ~Q4YBED4 | sadi-proto serial backend: config, port filter, purge/close, overflow |
| `docs/device/hwprobe.md` | ~X42K86Y | hwprobe tool: scripted probe, raw capture and replay Transport |
| `docs/device/python-binding.md` | ~QTAS277 | sadi-py: PyO3/maturin core bindings (Session, devices, numpy blocks) |
| `docs/device/serial.md` | ~Q4YBED4 | serialport backend over the FTDI VCP (Transport impl) |
| `docs/device/session.md` | ~SB1MWFD | sadi-proto session: connect/query/reset/start/stop state machine with retries |
| `docs/device/sim-byte-faults.md` | ~ZCE4AHC | Simulator byte-level faults: dropped, duplicated, corrupted, truncated bytes |
| `docs/device/sim-faults.md` | ~8XCPH41 | Simulator physics and signal faults: wire, LVDT, noise, drift, creep, slip, saturation |
| `docs/device/simulator.md` | ~CSWAMV8 | Simulator device: protocol-faithful SADI v1.003 Transport |
| `docs/device/v3.md` | ~2GGPZ5K | Optional: v3.41 codec (CRC-16/CCITT-FALSE framing) |
| `docs/e2e.md` | ~GW7ER11 | Browser e2e (Playwright) on 3 OS: full guided run against the simulator |
| `docs/hardware-verification.md` | ~CTSXSRE | Run hardware session and fold findings back (needs the physical board) |
| `docs/hardware/**` | ~CTSXSRE | Run hardware session and fold findings back (needs the physical board) |
| `docs/img/ui/**` | ~JS6PJJY | User guide: running a test with the app (procedure, two specimens, creep) |
| [`docs/jobs/jobs.md`](jobs/jobs.md) | ~V9NMTHC | Job system core: lifecycle state machine, process pool, cancel and supersede (latest wins) |
| [`docs/jobs/tasks.md`](jobs/tasks.md) | ~PX6X3ZQ | Progressive background jobs: Monte Carlo interval refinement |
| `docs/jobs/testing.md` | ~VAX9DG6 | Deterministic job test harness: fake clock, controllable scheduler, inline executor |
| `docs/launcher.md` | ~0VYJVFZ | `sadi` launcher: serve UI + API, pick port, open browser, flags |
| `docs/lctt/calibration.md` | ~NQKWT3Y | LCTT calibration: LINEST-equivalent fit with standard errors and t95 |
| [`docs/lctt/capture.md`](lctt/capture.md) | ~QPQKQEK | Capture modes: human confirm key, auto-capture with max wait, forced-early |
| `docs/lctt/clamp-check.md` | ~DQ1C3W6 | Pre-test clamp-slip check procedure |
| [`docs/lctt/live-results.md`](lctt/live-results.md) | ~19WDD6Q | Live recompute engine: all results after every captured point |
| `docs/lctt/creep.md` | ~7NDJSG8 | Creep fit: strain vs log-time per hold |
| `docs/lctt/slip.md` | ~T3M5GJG | Slip detector: sudden strain steps without load change |
| `docs/lctt/export-csv.md` | ~7P8582F | CSV export in the 32-column LabVIEW schema |
| `docs/lctt/guidance.md` | ~G2YNMJB | Guided run engine: phase-wise next-step guidance and confidence status |
| `docs/lctt/lab-module.md` | ~XMK16Q2 | Two-specimen workflow: long (elastic) and short (plastic) sample runs |
| `docs/lctt/live-results.md` | ~19WDD6Q | Live recompute engine: update all results after every captured point |
| `docs/lctt/loading.md` | ~9TZ8D2S | LCTT tare and strain/stress/load with RSS uncertainty |
| `docs/lctt/modulus.md` | ~TQ7ZKZW | LCTT E fit (selectable window), r^2, secant E, yield, saturation warning |
| `docs/lctt/settle.md` | ~7Q9BX19 | Settle detector: rolling LVDT drift slope, threshold and minimum dwell |
| `docs/lctt/slip.md` | ~T3M5GJG | Slip detector: sudden strain steps without load change |
| `docs/live-view.md` | ~KR3SSE1 | Live-view UX design: readouts, trace, indicators, stress-strain, guidance placement |
| `docs/packaging.md` | ~ZKJSYXC | Packaging: bundle built UI into the sadi wheel, entry points |
| `docs/portability.md` | ~PVJNZ7V | Portability audit: serial ports, drivers, udev, paths, line endings |
| `docs/python-layout.md` | ~XDK2EVN | Python scaffold: uv project, ruff, typani lint, pytest, core/ and labs/ layout |
| `docs/release.md` | ~JX9JXZ4 | Wheels and release workflow with install smoke test (maturin, 3 OS) |
| `docs/server/api.md` | ~X3H80G2 | FastAPI app: REST endpoints (sessions, points, results, export) |
| `docs/server/results-stream.md` | ~ETJKV0D | Versioned results stream: instant analytic, progressive refinement, stale markers |
| `docs/server/websocket.md` | ~4QRM2GS | Binary WebSocket stream: trace frames, state and result push |
| `docs/store/crash-testing.md` | ~HAH4MTB | Crash-recovery tests: kill the process mid-write on every OS |
| `docs/store/durable.md` | ~JA5DMTN | store/durable: cross-OS fsync, dir-fsync, atomic replace, exclusive create |
| `docs/store/csv-export.md` | ~K79AJH0 | store/csv_export: byte-exact UTF-8 CRLF CSV writer, no overwrite, gitattributes eol |
| `docs/store/events.md` | ~K6BT3MG | store/events+snapshot: point/edit event log, atomic snapshots, replay |
| `docs/store/exports.md` | ~36JQFXT | store/exports: derived exports with provenance, tmp + rename |
| `docs/store/session.md` | ~GCJAR1J | store/session: versioned O_EXCL session dirs, manifest, lock, resume |
| `docs/store/spill.md` | ~JQPFW6F | store/spill: import emergency spill files as a new session version |
| `docs/store/names.md` | ~T5XVYE8 | store/names: portable filename sanitiser, hash disambiguation, no-overwrite unique names |
| `docs/store/wal.md` | ~4668M06 | store/wal: append-only checksummed fsynced writer, reader, recovery |
| `docs/store/writer-thread.md` | ~3F2W55E | WAL writer thread: bounded queue, backpressure metrics, fsync off the acquisition path |
| `docs/testing.md` | ~WKK27QJ | Backend e2e suite: simulator fault injection (noise, drift, creep, slip, dropped bytes, saturation) |
| `docs/uncertainty/budget.md` | ~M0XPX0J | Sensitivity coefficients and uncertainty budget (per-input contribution) |
| `docs/uncertainty/crosscheck.md` | ~QTA833F | Uncertainty cross-check suite on every lab formula (analytic vs MC vs finite difference) |
| `docs/uncertainty/fallbacks.md` | ~FBSDE1R | Fallbacks: numeric-derivative path and Monte Carlo path (method="mc") |
| `docs/uncertainty/measured.md` | ~SP19B1H | sadi.uncertainty core: Measured value type, covariance, units, provenance |
| `docs/uncertainty/naming.md` | ~66MX8BW | Name-collision check against typani exports (lint/grep gate) |
| `docs/uncertainty/uncertain.md` | ~2NVD83Y | @uncertain decorator: sympy tracing, lambdify, full-covariance RSS, .symbolic/.latex/.partials |
| `docs/usability-report.md` | ~W5XJBZT | Usability pass: scripted walkthrough, issue log and fixes |
| `docs/user-guide.md` | ~JS6PJJY | User guide: running a test with the app (procedure, two specimens, creep) |
| `docs/ux.md` | ~GKVPN2E | UX design doc: wizard flow, step rail, wireframes (ASCII), keyboard map |
| `docs/web-layout.md` | ~21F3H53 | Web scaffold: Vite + React + TypeScript, lint, vitest, API client |
| `docs/web/budget-panel.md` | ~61M215J | Uncertainty budget and formula panel: dominant input, rendered LaTeX derivation |
| `docs/web/calibration-plot.md` | ~DDAPA9P | Calibration plot: fit with CI band, equation annotation and residuals |
| `docs/web/creep-plot.md` | ~7WJVKMW | Creep plot: strain vs log-time per hold with fit and slip markers |
| `docs/web/export-screen.md` | ~H8WGMBV | Results/Export screen: report view, figure export, CSV download |
| `docs/web/guidance.md` | ~9EFDXQE | Guidance UI: next-step panel, confidence meter, stop-early recommendation |
| `docs/web/live-trace.md` | ~7KWS2S7 | Live trace plot: scrolling binary-WebSocket trace with settle markers |
| `docs/web/plots.md` | ~MQYWW87 | Plot renderer core: publication-quality canvas, annotations, one-click PNG/SVG export |
| `docs/web/results-panel.md` | ~9PMPWH8 | Results panel: best value +/- U, 95% interval, plain-language confidence |
| `docs/web/wizard.md` | ~2ZQVKAB | Wizard shell: step rail, next-action panel, status bar, keyboard map |
| `docs/web/results-stream.md` | ~4XEGRNJ | Results-stream client: version/stale marker and refinement progress in the UI |
| `docs/web/review-screen.md` | ~FHNEDX8 | Review screen: re-edit points, window edits, undo/redo, results recompute |
| `docs/web/run-screens.md` | ~74FQXWT | Run screens: calibrate, tare, elastic, plastic capture screens with live view |
| `docs/web/stress-strain-plot.md` | ~3MJNBZY | Stress-strain plot: live E fit, selectable window, 0.2% offset yield |
| `docs/web/wizard.md` | ~2ZQVKAB | Wizard shell: step rail, next-action panel, status bar, keyboard capture |
