+++
id = "01M725CA43JK1ZDJKF8135RHT0"
title = "LCTT: tare uncertainty is the mean's SE (sd/sqrt(n)); name the creep allowance honestly"
type = "bug"
category = "in-progress"
priority = "low"
points = 2
reporter = "lognd"
created = "2026-11-10T07:22:23Z"
updated = "2026-11-10T07:25:20Z"
labels = ["creates:python/tests/labs/lctt/test_tare_unc.py"]
scope = ["python/sadi/labs/lctt/lab.py", "python/tests/labs/lctt/test_tare_unc.py", "docs/lctt/lab-module.md", "changelog.d/01M725CA43JK1ZDJKF8135RHT0.fixed.md"]

[[acceptance]]
text = "Tare quantity standard_uncertainty equals sd/sqrt(n) of the last tare block, covered by a test; docs note the creep allowance is a stated systematic"
bound = true
+++
