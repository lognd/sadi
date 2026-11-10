+++
id = "01M72PGMY61ANRVTM7EK7B4HZG"
title = "Live trace canvas distorted: keep scene aspect ratio when CSS scales width"
type = "bug"
category = "done"
outcome = "done"
priority = "high"
points = 3
reporter = "lognd"
created = "2026-11-10T12:21:51Z"
updated = "2026-11-10T12:24:48Z"
labels = ["web"]
scope = ["web/src/plots/core/canvas.ts", "web/src/plots/core/canvas.test.ts", "web/src/components/live/*", "web/src/plots/live/*"]

[[acceptance]]
text = "Canvas keeps scene width/height ratio at any container width (aspect-ratio set, inline height not fixed); vitest asserts style.aspectRatio; text not stretched"
bound = true
+++
