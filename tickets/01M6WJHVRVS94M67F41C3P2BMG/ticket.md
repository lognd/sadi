+++
id = "01M6WJHVRVS94M67F41C3P2BMG"
title = "doctor: DEV, SIM, WRK layers"
type = "bug"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-08T03:17:10Z"
updated = "2026-11-08T03:50:07Z"
scope = ["python/sadi/doctor/**", "python/tests/doctor/**", "docs/doctor.md", "docs/doctor-checks.md"]

[[acceptance]]
text = "Every DEV (010..050), SIM (010, 020) and WRK (010, 020) check is implemented read-only with a remedy for every failure mode on linux, wsl, windows and macos"
bound = true

[[acceptance]]
text = "With no board or no sadi_py the DEV and SIM checks skip informationally (no-device / tool-missing) and never crash"
bound = true

[[acceptance]]
text = "DEV-040 and DEV-050 run only with --stream-seconds / --with-reset"
bound = true

[[acceptance]]
text = "A spawned worker does not import sadi.store, and docs/doctor.md and docs/doctor-checks.md are current"
bound = true
+++

found while working ~V3H5CGF: spec layers not implemented
