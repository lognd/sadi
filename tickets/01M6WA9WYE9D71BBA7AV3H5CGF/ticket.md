+++
id = "01M6WA9WYE9D71BBA7AV3H5CGF"
title = "Implement sadi doctor: check runner, checks, step-by-step remediation (CLI)"
type = "task"
category = "in-progress"
priority = "high"
points = 5
reporter = "lognd"
created = "2026-11-08T00:53:00Z"
updated = "2026-11-08T03:17:46Z"
labels = ["model:sonnet", "ws:srv", "creates:python/sadi/doctor/**", "creates:python/tests/doctor/**", "creates:docs/doctor-checks.md"]
scope = ["python/sadi/doctor/**", "python/tests/doctor/**", "docs/doctor-checks.md", "python/pyproject.toml", "docs/doctor.md", "docs/README.md", "docs/index.md"]

[[links]]
kind = "blocked-by"
target = "01M6WA9WWV6GD9VCX7XJPRPASC"

[[acceptance]]
text = "sadi doctor runs every catalogued check read-only, never mutating data, and reports pass/warn/fail/skip with evidence"
bound = true

[[acceptance]]
text = "Every failing check prints numbered step-by-step remediation with exact commands for the detected OS and a verify step"
bound = false

[[acceptance]]
text = "Tests inject failures for each check via fixtures and assert the remediation text; JSON output validates against the pydantic schema"
bound = false
+++
