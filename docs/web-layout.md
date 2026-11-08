# Web layout

Status: current

`web/` is the Vite + React + TypeScript UI (strict TS, ESLint, vitest).
`web/package.json` is owned by F1 (~21F3H53); later tickets must not edit it.

Commands (in `web/`): `npm run dev` (proxy `/api` and `/ws` to FastAPI on
`SADI_API_PORT`, default 8000), `npm run typecheck`, `npm run lint`,
`npm test`, `npm run gen:api` (regenerate `src/api/schema.ts` from the
OpenAPI document; the checked-in file is a stub until B4 lands).

Diagnostics go through `src/api/log.ts` (`getLogger`), never `console`.
API calls return `Result<T, ApiError>` (`src/api/result.ts`), not throws.

## src/ ownership

| Path | Ticket |
|---|---|
| `src/api/`, `src/state/`, `src/main.tsx`, `src/App.tsx` | F1 ~21F3H53 |
| `src/components/plots/` (renderer core) | F3 ~MQYWW87 |
| `src/components/plots/trace*` | F4 ~7KWS2S7 |
| `src/components/plots/calibration*` | F5 ~DDAPA9P |
| `src/components/plots/stressStrain*` | F6 ~3MJNBZY |
| `src/components/plots/creep*` | F7 ~7WJVKMW |
| `src/components/results/` | F8 ~9PMPWH8, F16 ~4XEGRNJ |
| `src/components/wizard/` | F9 ~2ZQVKAB |
| `src/screens/setup/` | F10 ~AEZAQ6K |
| `src/screens/run/` | F11 ~74FQXWT |
| `src/components/guidance/` | F12 ~9EFDXQE |
| `src/screens/review/` | F13 ~FHNEDX8 |
| `src/screens/export/` | F15 ~H8WGMBV |
| `src/components/budget/` | F17 ~61M215J |

New store slices live in `src/state/<slice>.ts` and are composed into
`AppState` in `src/state/store.ts` by the owning ticket (widen scope).

CI runs the web lint, typecheck, test and build steps on all three OSes; see [Continuous integration](ci.md).
