+++
id = "01M6XAASH92DG6W6GDJBJVWSNR"
title = "Run: clearer message when a step stops with device_fault and zero points (U-06)"
type = "task"
category = "done"
outcome = "done"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-08T10:12:44Z"
updated = "2026-11-08T10:14:08Z"
scope = ["web/src/hooks/stopText.ts", "web/src/hooks/stopText.test.ts", "web/src/hooks/useTrace.ts", "web/src/plots/live/live.test.tsx", "docs/usability-report.md", "web/src/screens/run/RunScreen.usability.md"]

[[acceptance]]
text = "A server stop (device_fault) renders plain language with next steps (Doctor, check cable) and, with zero points captured, says to capture a point first"
bound = true
+++
