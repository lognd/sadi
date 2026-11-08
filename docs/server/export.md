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
