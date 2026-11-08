# Web API client generation

The backend OpenAPI document is committed at `web/src/api/openapi.json` and the TypeScript
types generated from it at `web/src/api/schema.ts`.

Regenerate both after any route or schema change:

    cd web && npm run gen:api     # gen:spec (python dump) then gen:ts (openapi-typescript)

- `python/sadi/server/openapi_export.py` dumps `create_app().openapi()` as sorted-key JSON
  (no server needed).
- Drift checks: `python/tests/server/test_openapi_export.py` fails if `openapi.json` is stale;
  `web/src/api/schema.test.ts` fails if `schema.ts` differs from the generator output.
- Only `openapi-typescript` (already a web devDependency) is used for generation; it was run
  locally for this change, but no CI job runs `gen:api` itself, only the drift tests.
- `Health` in `client.ts` is hand-declared: the backend has no `/api/health` route yet.
