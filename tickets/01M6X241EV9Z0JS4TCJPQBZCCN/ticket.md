+++
id = "01M6X241EV9Z0JS4TCJPQBZCCN"
title = "Run screen has no capture input entry (volts/height, mean/n, diameter, mass)"
type = "bug"
category = "in-progress"
priority = "high"
points = 5
reporter = "lognd"
created = "2026-11-08T07:49:14Z"
updated = "2026-11-08T08:11:26Z"

[[acceptance]]
text = "Run screen shows per-phase input fields and sends them; vitest covers validation"
bound = false
+++

found while working ~M84ZB2J: RunScreen sends empty inputs so POST capture returns 422 'calibration needs volts and height'; guided-run and run-capture e2e fail at capture after Settled. Needs input fields per phase (see core/point_inputs.py parse_inputs).
