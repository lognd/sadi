+++
id = "01M71VN3JDC5NDPJ2AW60KQX63"
title = "Web: loud SYNTHETIC DATA banner in instrument bar, session, results, export"
type = "story"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-10T04:32:25Z"
updated = "2026-11-10T04:37:10Z"
scope = ["web/src/**", "docs/web/**"]

[[acceptance]]
text = "When health or a session payload has data_provenance synthetic, a high-contrast SYNTHETIC DATA banner is always visible in the instrument bar on every page and in session, results and export views"
bound = true

[[acceptance]]
text = "Real data never shows the banner; exported filenames and download UI show the SYNTHETIC- prefix; vitest covers both states; docs/web updated"
bound = false
+++
