+++
id = "01M6WTCAA5WR1VD7H7ES7757MP"
title = "Resume should fold parent state into the new WAL version"
type = "task"
category = "done"
outcome = "done"
priority = "medium"
points = 3
parent = "01M6W7R09P668G2VDDAWEDCSRM"
reporter = "lognd"
created = "2026-11-08T05:33:56Z"
updated = "2026-11-08T05:36:56Z"
scope = ["python/sadi/server/service.py", "python/tests/server/test_resume_fold.py"]

[[links]]
kind = "blocked-by"
target = "01M6W7R3XY1B0BF689RX3H80G2"

[[acceptance]]
text = "Resume should fold parent state into the new WAL version"
bound = true

[[acceptance]]
text = "Resume copies parent POINT/EDIT/SETTINGS/MARKER records into the child WAL; parent unchanged"
bound = true
+++

found while working ~X3H80G2 (split out of its original acceptance). resume creates a fresh WAL; the child does not see the parent's points or wizard state.
