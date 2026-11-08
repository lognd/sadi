+++
id = "01M6WM63C59QDCSJ6HD48GN3NY"
title = "Plot core: error bars, band highlight, annotation collision avoidance"
type = "task"
category = "done"
outcome = "wont-fix"
priority = "medium"
reporter = "lognd"
created = "2026-11-08T03:45:41Z"
updated = "2026-11-08T03:47:25Z"
scope = ["web/src/plots/core/**"]
+++

found while working 01M6W7R3KN3HXVMJQ1D3MJNBZY: stress-strain emits uncertainty bars as many two-point line series (legend false) and window shading as a flat band; core should offer generic Series xErr/yErr bars with caps, annotation placement avoiding data and other boxes, and cheap incremental redraw for live updates. Then simplify stressstrain/buildScene.ts.
