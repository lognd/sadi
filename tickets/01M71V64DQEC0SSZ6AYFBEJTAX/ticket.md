+++
id = "01M71V64DQEC0SSZ6AYFBEJTAX"
title = "Regenerate web/src/api/openapi.json for DataProvenance fields"
type = "bug"
category = "done"
outcome = "duplicate"
priority = "medium"
reporter = "lognd"
created = "2026-11-10T04:24:14Z"
updated = "2026-11-10T04:32:29Z"
scope = ["web/src/api/openapi.json"]
+++

found while working E6MY8YC: new provenance fields on session/plot/results/health/stress-strain models make tests/server/test_openapi_export.py::test_committed_spec_not_stale fail until 'cd web && npm run gen:api' is run. web/** is owned by another agent.
