+++
id = "01M723P32SR45XWMW7BE5QZE7H"
title = "Audit2 H2b: stop raw streaming once session finished/idle; free-space guard"
type = "bug"
category = "in-progress"
priority = "high"
points = 3
reporter = "lognd"
created = "2026-11-10T06:52:46Z"
updated = "2026-11-10T07:04:36Z"
labels = ["creates:python/tests/server/test_idle_raw.py"]
scope = ["python/sadi/server/live.py", "python/sadi/core/device.py", "python/tests/server/test_idle_raw.py", "docs/data-safety.md", "docs/server/app.md", "changelog.d/01M723P32SR45XWMW7BE5QZE7H.fixed.md"]

[[acceptance]]
text = "After Results/Export or idle timeout the raw stream stops writing WAL; low free disk blocks new capture with a clear problem; no recorded data is dropped"
bound = true
+++

See audit2.md HIGH 2 (backend part). Do not drop or truncate any recorded data.
