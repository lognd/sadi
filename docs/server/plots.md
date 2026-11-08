# REST API: plots

Status: current

Parent: [api.md](api.md)

Router `sadi.server.routes.plots.make_plots_router(svc)` (mounted by `create_app`) serves
per-phase plot data for the open session. Read-only: both payloads are derived on every
call from the replayed session events (`curve_source.session_events`); nothing is written.

| Endpoint | Returns |
| --- | --- |
| `GET /api/plots/calibration` | `CalibrationPlot`: `volts`, `height_m`, and `fit` (null below 3 points) |
| `GET /api/plots/stress-strain` | `StressStrainPlot`: `point_ids`, `strain`, `stress_mpa`, `excluded` |

- `fit` holds `slope_m_per_v`, `intercept_m`, `r2`, `n` and the 95% mean-height band over the
  sorted calibration volts (`band_volts`, `band_height_m`, `band_half_width_m`).
- Stress-strain rows come from the lctt export document derivation; excluded points are
  flagged, not dropped. Arrays are empty until the tare and specimen are recorded.
- Errors are problem+json: 409 `no_open_session` when nothing is open.
