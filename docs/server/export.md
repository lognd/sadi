# REST API: export

Status: current

Parent: [api.md](api.md)

Router `sadi.server.routes.export.make_export_router(svc, labs)` (mounted by `create_app`)
exposes the open session's lab `export_formats` (see `sadi.core.lab.ExportFormat`).

| Endpoint | Returns |
| --- | --- |
| `GET /api/export` | `ExportFormatView[]` (`id`, `title`, `media_type`, `download`) |
| `GET /api/export/{format}` | the rendered bytes with the format's media type |

- Non-JSON formats (CSV) are sent with `Content-Disposition: attachment;
  filename="<session>-<format>.<ext>"`. `application/json` formats are figure data for the
  web plots and are sent inline with no disposition.
- Read-only: the payload is rendered in memory from a live recompute of the active points
  (the same `session_points.analyze` path the results route uses, see [results](results.md))
  and sent as the response. Nothing is written to disk or the WAL, so no existing file can be
  overwritten. A future save-to-disk export must use `sadi.store.durable` temp + atomic
  rename and refuse to replace an existing file.
- Errors are problem+json with a `hint`: 409 `no_open_session`, 404 `unknown_id` for an
  unknown format (the hint lists the lab's formats), and the mapped compute error when the
  recompute or the writer fails.
- Writers receive raw session events: `render_export` replays the open session's log
  (`curve_source.session_events`, read-only) and passes them as `RunState.events`
  (opaque `BaseModel`s; the lab narrows them to its own event types). Labs that derive
  results from `CapturedPoint`/`AnalysisResult` alone can ignore the field.
- The lctt lab declares `lctt-csv` (see [lctt/export-csv.md](../lctt/export-csv.md)) and
  `lctt-figure-json` (see [lctt/figure-data.md](../lctt/figure-data.md)).

Events for the run state come from the shared `curve_source.SessionReplayCache` (the same incremental
replayer the plots and stress-strain routes use), not a full WAL walk per request; the result equals a
full replay and anomalies fall back to the verified full replay.

Export never serves unverified data: `render_export` calls `SessionReplayCache.events(path, verify=True)`,
which discards the cached replayer and runs a full CRC-verified replay, so corruption in WAL bytes the
incremental tail had already applied fails the export (replay error, nothing rendered).

## Read-only export of a closed session (~VBQ0A3E)

`GET /api/sessions/{name}/export/{format_id}` renders a closed session without Resume: it takes no writer lock, creates no version, appends nothing to the WAL, writes no copy and needs no device. `SessionService.read_closed` refuses with 409 `session_open` (the open session, or a live writer holds it), 409 `session_corrupt` (torn or corrupt WAL, or recovery fails) and 404 for unknown names; every refusal carries a hint and nothing on disk is modified. Rendering shares `_render` with `render_export`.

## Cross-site GET refusal and download names

- `OriginGuard` refuses any `/api/*` GET carrying `Sec-Fetch-Site: cross-site`
  (export GETs write a saved copy, so a foreign page must not trigger them).
  Same-origin, same-site, user-initiated (`none`) and header-less clients pass.
- When a response carries `X-SADI-Provenance`, the web client uses the server's
  `Content-Disposition` name verbatim (`RECOVERED-`/`SYNTHETIC-` prefixes are
  server-owned); the global provenance store is only a fallback for old replies.
- The stress-strain figure data carries a per-row `phase`; the E refit curve
  (`load_session_curve`) uses elastic rows only, never the plastic run.
