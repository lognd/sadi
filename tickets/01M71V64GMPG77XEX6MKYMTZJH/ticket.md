+++
id = "01M71V64GMPG77XEX6MKYMTZJH"
title = "lctt context_from_inputs uses one L0/specimen/tare for all points"
type = "bug"
category = "in-progress"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-10T04:24:15Z"
updated = "2026-11-10T15:45:14Z"
scope = ["python/sadi/labs/lctt/**"]
+++

found while working E6MY8YC: lab.py ~351-368 takes L0 from the last load point's phase and the last specimen and tare for every point, so the combined /api/plots/stress-strain is wrong for one of the elastic/plastic runs when both are in one session.
