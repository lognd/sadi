+++
id = "01M6WQ6E3HVJC599WZJVBT39Q9"
title = "Strengthen test_startup_ignores_spill_in_real_dir_standin to plant a spill where the app would look"
type = "task"
category = "in-progress"
priority = "low"
points = 1
reporter = "lognd"
created = "2026-11-08T04:38:18Z"
updated = "2026-11-08T05:05:32Z"
+++

python/tests/server/test_spill_isolation.py plants the spill outside any dir the app scans, so it proves little. Plant it in the real (HOME/XDG-derived) spill dir stand-in and assert the isolated app neither imports nor modifies it. Start after ~2C5G9GB lands (shared tests/server scope).
