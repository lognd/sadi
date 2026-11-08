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
  and sent as the response. Nothing is written to disk or the WAL, so no existing file can be
  overwritten. A future save-to-disk export must use `sadi.store.durable` temp + atomic
  rename and refuse to replace an existing file.
- Errors are problem+json with a `hint`: 409 `no_open_session`, 404 `unknown_id` for an
  unknown format (the hint lists the lab's formats), and the mapped compute error when the
  recompute or the writer fails.
- The lctt lab declares no formats yet, so its list is empty (follow-up for lab authors).
