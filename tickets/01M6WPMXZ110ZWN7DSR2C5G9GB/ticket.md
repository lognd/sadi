+++
id = "01M6WPMXZ110ZWN7DSR2C5G9GB"
title = "ty: clear diagnostics in python/tests (excluding tests/doctor)"
type = "task"
category = "in-progress"
priority = "low"
points = 3
reporter = "lognd"
created = "2026-11-08T04:28:44Z"
updated = "2026-11-08T04:29:04Z"
scope = ["python/tests/api/**", "python/tests/cli/**", "python/tests/core/**", "python/tests/jobs/**", "python/tests/labs/**", "python/tests/plugins/**", "python/tests/server/**", "python/tests/store/**", "python/tests/uncertainty/**"]
+++

Clear ty diagnostics under python/tests/** except python/tests/doctor/** (owned by in-flight doctor tickets). Fix annotations/fixtures properly; targeted ty: ignore with reason only where unavoidable. No test behaviour changes. Acceptance: ty check reports zero diagnostics for python/tests excluding doctor; suite passes.
