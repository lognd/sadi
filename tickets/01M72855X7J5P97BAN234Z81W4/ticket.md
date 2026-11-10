+++
id = "01M72855X7J5P97BAN234Z81W4"
title = "L7: fixed 11rem sticky offset collides at 800px height"
type = "bug"
category = "in-progress"
priority = "low"
points = 2
reporter = "lognd"
created = "2026-11-10T08:10:55Z"
updated = "2026-11-10T08:17:00Z"
scope = ["web/src/styles.css", "web/src/hooks/useStickyOffset.ts", "web/src/hooks/useStickyOffset.test.ts", "web/src/main.tsx", "docs/ux.md"]

[[acceptance]]
text = "Sticky offset derived from measured header height; no overlap at 800px"
bound = true
+++
