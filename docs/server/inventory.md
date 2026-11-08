# REST API: weight inventory

Status: current

Parent: [api.md](api.md)

Routes in `sadi.server.routes.inventory` (`make_inventory_router(svc, provider)`) are thin
handlers. The inventory model is supplied by a plugin through the `InventoryProvider` port
(`parse`, `snapshot`, `combo`); with no provider every route answers 501 problem+json with a
hint to enable one.

## Data safety

- An entry is validated by the provider, trial-folded with the prior events, then appended as
  a JSON NOTE record via `SessionService.append_note` and durable before the response.
- There are no deletes. Editing a weight is a later event for the same number; the view keeps
  the history. Rejected entries write nothing.
- NOTE records are copied into the child on resume (`_fold_parent`), so the inventory carries
  across session versions.

## Endpoints (prefix `/api/session/inventory`)

| Method and path | Purpose |
|---|---|
| GET `` | current view: weights with history, groups, reconciliation |
| POST `/weights` | add or edit a numbered weight; returns `{seq, inventory}` |
| POST `/groups` | record a group balance weighing of a named subset |
| POST `/combo` | derive the combination of `numbers` (read-only) |

Errors: no open session 409, provider refusal 422 (`urn:sadi:error:input:inventory_invalid`),
no provider 501; all `application/problem+json` with a `hint`.

## Wiring

The router is not yet mounted by `create_app`; wiring an `AppSettings.inventory` provider is a
follow-up (app.py was leased elsewhere).
