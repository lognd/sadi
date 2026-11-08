# LCTT figure-data export

Status: current

Parent: [lab-module.md](lab-module.md)

The `lctt-figure-json` export format (`sadi.labs.lctt.lab.FIGURE_FORMAT`, media type
`application/json`) renders the series behind the calibration and stress-strain plots,
in memory, from `RunState.events`.

Document (`sadi.labs.lctt.figure_data.FigureData`):

- `calibration`: `volts`, `height_m`, and `fit` (null below 3 points) with slope, intercept,
  r2, n and the 95% confidence band.
- `stress_strain`: `point_ids`, `strain`, `stress_mpa`, `excluded` (excluded points are
  flagged, not dropped); empty until the specimen and tare are recorded.

A session with no recorded inputs is refused with `TOO_FEW_POINTS`. The derivation lives here and
`sadi.server.routes.plots` adapts it; the lab package does not import server code.
