+++
id = "01M6WP4WV9B3SCJ0GY2M32XWZV"
title = "Launcher startup must call spill.import_all_spills after taking the data-root lock"
type = "bug"
category = "in-progress"
priority = "high"
points = 2
reporter = "lognd"
created = "2026-11-08T04:19:59Z"
updated = "2026-11-08T04:21:17Z"
labels = ["creates:python/tests/cli/test_launcher_spill.py"]
scope = ["python/sadi/server/app.py", "python/tests/cli/test_launcher_spill.py", "docs/store/spill.md"]

[[acceptance]]
text = "A spill present at startup is imported into a new session version after the lock is taken"
bound = true

[[acceptance]]
text = "A failed import leaves the spill file intact and is reported"
bound = true

[[acceptance]]
text = "No spill file is a no-op"
bound = true
+++

Emergency spill files are only imported if import_all_spills runs; nothing calls it at startup, so spilled points would sit unseen (data-safety mandate). Wire it into the sadi launcher/create_app startup after the data-root lock is held, log each imported spill, surface failures without deleting spill files (never auto-overwrite). Scope: python/sadi/cli/**, python/sadi/store/spill.py (read), python/tests/cli/**, docs/.
