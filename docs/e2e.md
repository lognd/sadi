# Browser e2e (Playwright)

Status: current

Parent: [Documentation index](index.md). Ticket: ~GW7ER11 (also covers ~A7JNFGT, run-screen capture).

Playwright (chromium only) drives `sadi --sim` through the guided run with the keyboard only.
See [UX](ux.md) for the key map and [user guide](user-guide.md) for the procedure.

## Layout

- `web/e2e/playwright.config.ts`: one worker, chromium, no shared server (see fixtures.ts).
- `web/e2e/fixtures.ts`: overrides `baseURL` so every test starts its own `sadi --sim --no-browser` on a free
  port (searched upward from `SADI_E2E_PORT`, default 8765) with a fresh temp data dir, removed after the test.
  Real session data is never read, written or deleted and no session is shared between specs.
- `web/e2e/guided-run.spec.ts`: Setup to Export; asserts the results panel, a non-empty CSV
  download (F3) and a non-empty PNG figure download.
- `web/e2e/run-capture.spec.ts`: calibrate/tare/elastic/plastic capture phases (~A7JNFGT).
- `web/e2e/screenshots.spec.ts`: opt-in (`SADI_SCREENSHOTS=1`, skipped otherwise); regenerates `docs/img/ui/*.png`
  used by the [user guide](user-guide.md) (~921XDAW).
- `.github/workflows/e2e.yml`: ubuntu, windows and macos matrix.

## Running locally

```
uv sync --frozen --project python          # plus maturin develop for sadi_py (simulator)
uv run --project python python packaging/build_ui.py
cd web && npx playwright install chromium
npx playwright test -c e2e/playwright.config.ts
```

On Debian/Ubuntu/WSL chromium needs system libraries: `sudo npx playwright install-deps chromium`
(or `sudo apt install libnspr4 libnss3 libasound2t64`). Without them the browser exits 127.

## Mounting

`web/src/App.tsx` mounts `WizardHost` (`web/src/screens/WizardHost.tsx`) under the health line and
the Doctor link. The host reads the wizard rail and shows the screen for the current step: Setup
note, run screens (calibrate, tare, elastic, plastic), review (Results) and export (Export, F3 saves
the CSV). The step rail is visible on every step. The specs wait up to 10 s for the "Steps"
navigation and skip only if it never appears (backend down). Selectors follow the components: the
calibration step title is "LVDT calibration", so the specs match `calibration`/`LVDT calibration`
rather than "Calibrate" (the run heading still says "Calibrate").

## Session setup and known gaps

`openWizard` closes the Doctor panel if it opened (the backend has no `/api/health` route, so the
app treats the probe as a connection error; filed as a bug) and, when the Setup screen is shown,
creates a fresh session through its form (never resumes or discards one). If no lab is registered
(the launcher does not wire plugin labs yet; filed as a bug) the form cannot submit and the specs
skip. `fixtures.ts` passes `--web-dist web/dist` (run `npm run build` first); readiness is polled at
`/openapi.json`. Run with `PYTHONPATH=crates/sadi-py/python` when `sadi_py` is not installed in the
python venv. Playwright output dirs `test-results/` and `playwright-report/` are gitignored.

Setup needs captured clamp-check points and the UI has no capture screen for it yet, so the specs
leave Setup with "Skip this step" (`skipSetup`).
Under `--sim` the launcher opens the simulator with a manual load program (`DeviceSource.manual_load`):
the load is flat until `POST /api/session/load-change` steps it by `SIM_LOAD_STEP_KG` through
`DeviceService.sim_add_weight`, so successive calibration points get distinct volts and E is computed.
Real hardware is unaffected (`is_simulator` is false). The guided run does not download the LCTT CSV
because no wizard step captures the specimen it needs (filed as a bug); it asserts that the figure export buttons render (the PNG download itself never fires; filed as ~935NES4). The launcher now wires a live acquisition pipeline (simulator under `--sim`), so `/api/stream`
is mounted and the readout updates once a session is open (see server/launcher.md).
`acceptWhenSettled` first presses "Mark load change" (POST /api/session/load-change, recorded as a WAL
marker) so the detector can settle and the readout reaches `[Settled]`.
The Run screen has per-phase input fields (see web/run-screens.md); `acceptWhenSettled(page, inputsFor(phase, i))`
fills them, leaves the field (hotkeys are ignored in text inputs), marks a load change, waits for the
marker ack and `[Settled]`, then presses Space. Known gaps (tickets): capture latency grows with WAL
size so the full guided run does not finish (~2RWJ137). Each test has its own backend, so specs start at Setup (fixed in ~DKZDSBS).
