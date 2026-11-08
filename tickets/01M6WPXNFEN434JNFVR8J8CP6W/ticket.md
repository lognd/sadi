+++
id = "01M6WPXNFEN434JNFVR8J8CP6W"
title = "Clear ty diagnostics in python/sadi/doctor and python/tests/doctor"
type = "task"
category = "in-progress"
priority = "low"
points = 3
reporter = "lognd"
created = "2026-11-08T04:33:31Z"
updated = "2026-11-08T04:33:55Z"
scope = ["python/sadi/doctor/**"]
+++

ty reports ~125 diagnostics in doctor sources and tests. Fix without behavior change; add an acceptance command evidence: ty check on both paths reports zero. Start after ~4ZPY9YT lands (shared doctor scope).
