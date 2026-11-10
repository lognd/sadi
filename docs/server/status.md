# REST API: status

Status: current

Parent: [api.md](api.md)

`GET /api/status` (`sadi.server.routes.status.make_status_router`) returns
`{firmware, sample_rate_hz, data_root}`.

- `data_root` is the ACTIVE `--data-root` the app was built with (resolved), not the doctor default.
- `firmware` is the device firmware string, `"unknown"` when the device does not report one
  (the same value written to the session settings records); `null` with no live acquisition.
- `sample_rate_hz` is the effective decimated frame rate; `null` with no live acquisition.

The web debug strip polls it and shows Firmware and Sample rate from it.
