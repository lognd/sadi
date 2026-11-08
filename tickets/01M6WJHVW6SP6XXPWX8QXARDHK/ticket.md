+++
id = "01M6WJHVW6SP6XXPWX8QXARDHK"
title = "doctor: DATA-040..080, RES-040, CLK-020..040"
type = "bug"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-08T03:17:10Z"
updated = "2026-11-08T04:13:44Z"
scope = ["python/sadi/doctor/**", "python/tests/doctor/**", "docs/doctor.md", "docs/doctor-checks.md"]

[[acceptance]]
text = "Every declared mode of DATA-040..080, RES-040 and CLK-020..040 is reproduced by fault injection with a verified remediation for all four OSes"
bound = true

[[acceptance]]
text = "DATA-040 writes only with --allow-probe-write and leaves no probe file behind"
bound = false

[[acceptance]]
text = "docs/doctor-checks.md matches the generated catalog"
bound = false
+++

found while working ~V3H5CGF: deferred checks
