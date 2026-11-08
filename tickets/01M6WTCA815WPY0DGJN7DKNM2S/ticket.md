+++
id = "01M6WTCA815WPY0DGJN7DKNM2S"
title = "Loop-lag test: handlers stay under latency budget while jobs run"
type = "task"
category = "todo"
priority = "medium"
points = 2
parent = "01M6W7R09P668G2VDDAWEDCSRM"
reporter = "lognd"
created = "2026-11-08T05:33:56Z"
updated = "2026-11-08T05:37:20Z"
scope = ["python/tests/server/test_loop_lag.py"]

[[links]]
kind = "blocked-by"
target = "01M6W7R3XY1B0BF689RX3H80G2"

[[acceptance]]
text = "Loop-lag test: handlers stay under latency budget while jobs run"
bound = false
+++

found while working ~X3H80G2 (split out of its original acceptance). Proves no CPU-heavy work on the asyncio loop.
