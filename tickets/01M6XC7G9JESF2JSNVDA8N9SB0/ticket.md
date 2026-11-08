+++
id = "01M6XC7G9JESF2JSNVDA8N9SB0"
title = "Fix tsc stage command so web COV001 resolves on main"
type = "bug"
category = "in-progress"
priority = "medium"
points = 1
reporter = "lognd"
created = "2026-11-08T10:45:53Z"
updated = "2026-11-08T10:47:13Z"
scope = ["frob.toml"]

[[acceptance]]
text = "frob check on main reports zero COV001 under web/src"
bound = true
+++

found while working ~5PCC2QG: npx tsc at the repo root runs the wrong tsc package; use npm --prefix web exec -- tsc. Acceptance: zero web COV001 on main.
