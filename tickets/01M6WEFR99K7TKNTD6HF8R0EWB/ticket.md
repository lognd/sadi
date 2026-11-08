+++
id = "01M6WEFR99K7TKNTD6HF8R0EWB"
title = "Doctor: apply approved decisions (psutil, read-only data-dir fix, exit codes, unverified channel probe) and promote drafts"
type = "docs"
category = "done"
outcome = "done"
priority = "medium"
points = 3
parent = "01M6W7R00Z87A80RZB3JCC7HDM"
reporter = "lognd"
created = "2026-11-08T02:06:06Z"
updated = "2026-11-08T02:07:48Z"
idempotency_key = "sadi-doctor-decisions"
scope = ["docs/doctor.md", "docs/gp-selector.md", "docs/portability.md", "python/pyproject.toml", "python/uv.lock"]

[[acceptance]]
text = "docs/doctor.md states: psutil is the system-metrics dependency; doctor fix never modifies the user data dir; runs with warnings only exit 0; the FTDI channel A/B probe is reported as unverified until hardware exists"
bound = true

[[acceptance]]
text = "psutil is added to python/pyproject.toml dependencies and uv.lock is regenerated"
bound = true

[[acceptance]]
text = "docs/doctor.md, docs/gp-selector.md and docs/portability.md move from Status: draft to current once the decisions above are applied"
bound = true
+++
