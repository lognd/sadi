+++
id = "01M6XAASH92DG6W6GDJBJVWSNR"
title = "Run: clearer message when a step stops with device_fault and zero points (U-06)"
type = "task"
category = "in-progress"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-08T10:12:44Z"
updated = "2026-11-08T10:13:47Z"
scope = ["web/src/hooks/stopText.ts", "web/src/hooks/stopText.test.ts", "web/src/hooks/useTrace.ts"]

[[acceptance]]
text = "A server stop (device_fault) renders plain language with next steps (Doctor, check cable) and, with zero points captured, says to capture a point first"
bound = false
+++
