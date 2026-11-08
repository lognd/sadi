+++
id = "01M6WPMXX26BTCK9VP2CP7ERWV"
title = "ty: clear diagnostics in python/sadi (excluding doctor)"
type = "task"
category = "in-progress"
priority = "low"
points = 3
reporter = "lognd"
created = "2026-11-08T04:28:44Z"
updated = "2026-11-08T04:29:13Z"
scope = ["python/sadi/cli/plugins.py", "python/sadi/core/phases.py"]
+++

uv run --frozen ty check reports ~250 diagnostics project-wide; this ticket clears those under python/sadi/** except python/sadi/doctor/** (doctor is covered by in-flight doctor tickets). Fix real typing issues (no blanket ignores; a targeted ty: ignore with a reason only where a library stub is wrong). No behaviour changes. Acceptance: ty check reports zero diagnostics for python/sadi excluding doctor; existing tests pass.
