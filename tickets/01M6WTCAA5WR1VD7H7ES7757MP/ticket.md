+++
id = "01M6WTCAA5WR1VD7H7ES7757MP"
title = "Resume should fold parent state into the new WAL version"
type = "task"
category = "todo"
priority = "medium"
points = 3
parent = "01M6W7R09P668G2VDDAWEDCSRM"
reporter = "lognd"
created = "2026-11-08T05:33:56Z"
updated = "2026-11-08T05:34:30Z"
scope = ["python/sadi/server/service.py"]

[[links]]
kind = "blocked-by"
target = "01M6W7R3XY1B0BF689RX3H80G2"

[[acceptance]]
text = "Resume should fold parent state into the new WAL version"
bound = false
+++

found while working ~X3H80G2 (split out of its original acceptance). resume creates a fresh WAL; the child does not see the parent's points or wizard state.
