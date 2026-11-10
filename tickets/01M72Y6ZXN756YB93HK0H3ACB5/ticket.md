+++
id = "01M72Y6ZXN756YB93HK0H3ACB5"
title = "Square live trace pushes Accept 3 screens down below 64rem (audit8 M4)"
type = "bug"
category = "todo"
priority = "high"
points = 2
reporter = "lognd"
created = "2026-11-10T14:36:23Z"
updated = "2026-11-10T14:36:23Z"
labels = ["creates:web/src/plots/live/useContainerSquare.test.ts"]
scope = ["web/src/plots/live/useContainerSquare.ts", "web/src/components/live/TraceCanvas.tsx", "web/src/plots/live/**"]

[[acceptance]]
text = "Live trace side is clamped to min(containerWidth, 0.6*viewport height, 520) and stays square; Accept is inside the first viewport at 1024x768."
bound = false
+++

See /tmp/claude-1000/-home-logan-projects-SADI/4f193782-dc1d-4c66-a170-89d2ce998f4d/scratchpad/audit8.md section M4. Do not edit styles.css unless the lease allows.
