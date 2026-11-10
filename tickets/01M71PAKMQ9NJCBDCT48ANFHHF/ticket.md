+++
id = "01M71PAKMQ9NJCBDCT48ANFHHF"
title = "CI red on main: eslint redundant union in guidance/types.ts and stale committed OpenAPI spec"
type = "bug"
category = "in-progress"
priority = "high"
points = 1
reporter = "lognd"
created = "2026-11-10T02:59:18Z"
updated = "2026-11-10T02:59:26Z"
scope = ["web/src/components/guidance/types.ts", "web/src/api/**", "changelog.d/**"]

[[acceptance]]
text = "Given main, when eslint runs in web/, then no no-redundant-type-constituents error"
bound = false

[[acceptance]]
text = "Given the committed OpenAPI spec and schema.ts, when test_committed_spec_not_stale runs, then it passes"
bound = false
+++

CI run 42745837793 failed on web eslint (types.ts:42) and python test_committed_spec_not_stale.
