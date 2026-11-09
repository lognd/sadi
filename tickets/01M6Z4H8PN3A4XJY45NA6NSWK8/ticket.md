+++
id = "01M6Z4H8PN3A4XJY45NA6NSWK8"
title = "Migrate launcher.open_sim_device and doctor hostprobe/probes/checks/ext to devfacade (no raw sadi_py/pyserial)"
type = "task"
category = "in-progress"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-09T03:09:53Z"
updated = "2026-11-09T03:21:23Z"
idempotency_key = "facade-migrate-launcher-doctor"
scope = ["python/sadi/doctor/hostprobe.py", "python/sadi/launcher.py", "python/tests/doctor/test_sadi_doctor.py"]

[[acceptance]]
text = "hostprobe/launcher use devfacade; web_bundle_version looks in sadi/_ui then web/dist"
bound = true
+++
