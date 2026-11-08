+++
id = "01M6WM4ZDY9EHM2BW9312B5SEY"
title = "Plot core: label collision avoidance, log axes, sub-panels and zoom-aware decimation (shared by all plots)"
type = "task"
category = "in-progress"
priority = "medium"
points = 5
reporter = "lognd"
created = "2026-11-08T03:45:04Z"
updated = "2026-11-08T03:51:23Z"
scope = ["web/src/plots/core/**", "docs/web/plots.md"]

[[acceptance]]
text = "Label placement is greedy and deterministic: no placed box overlaps another or the legend, and results are identical across runs"
bound = false
+++

Generic features in web/src/plots/core so every plot (calibration, stress-strain, creep) shares one backend and renders adaptively: annotation placement that avoids data and other labels, log axis scale, stacked sub-panels (residuals), re-decimation on zoom/resize, band and marker primitives. No plot-specific drawing code outside core.
