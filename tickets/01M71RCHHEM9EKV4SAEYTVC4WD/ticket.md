+++
id = "01M71RCHHEM9EKV4SAEYTVC4WD"
title = "Web: LabVIEW-style front panel with persistent live readout on every step"
type = "story"
category = "in-progress"
priority = "high"
points = 8
parent = "01M6W7RAH93KKNK1WH67KWS2S7"
reporter = "lognd"
created = "2026-11-10T03:35:19Z"
updated = "2026-11-10T03:42:12Z"
scope = ["web/src/**", "docs/web/**"]

[[acceptance]]
text = "A live readout (LVDT volts, drift, settle state, connection, simulated banner) is visible on every wizard step incl. setup, results, export"
bound = true

[[acceptance]]
text = "A live trace plot is persistent beside the step content"
bound = false

[[acceptance]]
text = "Step rail is a left sidebar with plain-language titles; primary next action is prominent"
bound = false

[[acceptance]]
text = "Existing vitest suites pass; crunk check passes; data-safety text preserved"
bound = false
+++
