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

## Known gaps

`web/src/App.tsx` currently mounts only the health page and the Doctor; the wizard shell,
run, review and export screens are not routed. The specs detect a missing step rail and skip
with that reason, and start asserting as soon as the wizard is mounted. Selectors (export
button names, results region) are best-effort against the screen components and may need
adjusting at that point.
