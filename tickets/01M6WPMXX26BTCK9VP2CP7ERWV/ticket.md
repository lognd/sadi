+++
id = "01M6WPMXX26BTCK9VP2CP7ERWV"
title = "ty: clear diagnostics in python/sadi (excluding doctor)"
type = "task"
category = "in-progress"
priority = "low"
points = 3
reporter = "lognd"
created = "2026-11-08T04:28:44Z"
updated = "2026-11-08T04:29:15Z"
scope = ["python/sadi/cli/plugins.py", "python/sadi/core/phases.py", "python/sadi/core/device.py", "python/sadi/jobs/tasks/_drive.py", "python/sadi/jobs/tasks/gp.py", "python/sadi/jobs/tasks/mc.py", "python/sadi/labs/lctt/calibration.py", "python/sadi/labs/lctt/clamp_check.py", "python/sadi/labs/lctt/loading.py", "python/sadi/plugins/builtin.py", "python/sadi/plugins/local.py", "python/sadi/plugins/manifest.py", "python/sadi/plugins/registry.py", "python/sadi/plugins/settings.py", "python/sadi/plugins/sources.py"]
+++

uv run --frozen ty check reports ~250 diagnostics project-wide; this ticket clears those under python/sadi/** except python/sadi/doctor/** (doctor is covered by in-flight doctor tickets). Fix real typing issues (no blanket ignores; a targeted ty: ignore with a reason only where a library stub is wrong). No behaviour changes. Acceptance: ty check reports zero diagnostics for python/sadi excluding doctor; existing tests pass.
