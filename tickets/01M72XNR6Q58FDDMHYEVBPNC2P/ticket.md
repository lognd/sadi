+++
id = "01M72XNR6Q58FDDMHYEVBPNC2P"
title = "Restyle the web UI as a terminal: monospace font, dark-on-phosphor look, square plots kept"
type = "story"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-10T14:26:58Z"
updated = "2026-11-10T14:31:55Z"
scope = ["web/index.html", "web/src/styles.css", "web/src/tokens.css", "web/src/theme.css", "web/src/plots/theme.ts", "web/crunk.toml", "docs/web/design-system.md", "web/src/plots/calibration/__snapshots__/*", "web/src/plots/core/__snapshots__/*", "web/src/plots/creep/__snapshots__/*", "web/src/plots/stressstrain/__snapshots__/*"]

[[acceptance]]
text = "All text uses a monospace stack; terminal palette (dark background, high-contrast foreground) from one token file; status keeps glyph plus word; WCAG AA contrast; live and stress-strain plots stay square and read colours from the tokens; web vitest and tsc pass"
bound = false
+++
