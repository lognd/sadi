# Browser e2e (Playwright)

Status: current

Parent: [Documentation index](index.md). Ticket: ~GW7ER11 (also covers ~A7JNFGT, run-screen capture).

Playwright (chromium only) drives `sadi --sim` through the guided run with the keyboard only.
See [UX](ux.md) for the key map and [user guide](user-guide.md) for the procedure.

## Layout

- `web/e2e/playwright.config.ts`: one worker, chromium, starts the backend via `serve.mjs`.
- `web/e2e/serve.mjs`: runs `sadi --sim --no-browser` on port 8765 (`SADI_E2E_PORT`) with a fresh
  temp data dir, so real session data is never read, written or deleted.
- `web/e2e/guided-run.spec.ts`: Setup to Export; asserts the results panel, a non-empty CSV
  download (F3) and a non-empty PNG figure download.
- `web/e2e/run-capture.spec.ts`: calibrate/tare/elastic/plastic capture phases (~A7JNFGT).
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
skip. `serve.mjs` passes `--web-dist web/dist` (run `npm run build` first); the readiness URL is
`/openapi.json`. Run with `PYTHONPATH=crates/sadi-py/python` when `sadi_py` is not installed in the
python venv. Playwright output dirs `test-results/` and `playwright-report/` are gitignored.
