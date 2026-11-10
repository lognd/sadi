+++
id = "01M71MKBSXNE43ZJF2SEJ231JH"
title = "Adopt crunk design spec for web: crunk.toml tokens matching styles.css, crunk check clean, drift check in CI"
type = "task"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-10T02:29:08Z"
updated = "2026-11-10T02:51:47Z"
scope = ["web/crunk.toml", "web/src/styles.css", "web/src/screens/run/RunView.tsx", "docs/web/wizard.md", ".github/workflows/ci.yml", "web/src/tokens.css", "web/package.json", "web/src/theme.css", "web/src/a11y/contrast.test.ts", "web/.gitignore", "frob.toml"]

[[acceptance]]
text = "Given web/, when crunk check runs with a committed crunk.toml whose tokens mirror styles.css, then it reports no errors"
bound = false

[[acceptance]]
text = "Given the token export, when it is regenerated, then it matches the committed CSS variables (no TOKENS001 drift)"
bound = false
+++
