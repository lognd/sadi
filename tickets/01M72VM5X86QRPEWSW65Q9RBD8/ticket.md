+++
id = "01M72VM5X86QRPEWSW65Q9RBD8"
title = "Live trace sized from container (square, readable text); setup helper text; gauge height units"
type = "bug"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-10T13:51:09Z"
updated = "2026-11-10T13:51:49Z"
scope = ["web/src/plots/live/**", "web/src/plots/core/canvas.ts", "web/src/styles.css", "web/src/screens/setup/SessionSetup.tsx", "web/src/screens/run/designAdvice.ts"]

[[acceptance]]
text = "live scene width==height from ResizeObserver, rendered fonts >=12 CSS px; setup helper text sentence case at text-sm; gauge height suggestion shown in field unit (m) with mm in parentheses"
bound = false
+++

Audit7 M3, L3, L1. User complaint: live trace not square, text distorted.
