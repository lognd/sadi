+++
id = "01M6X465ZVYG4B9Y79QAZ8KDXT"
title = "curve_source and notes() still walk the whole WAL per request"
type = "bug"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-08T08:25:21Z"
updated = "2026-11-08T08:25:32Z"
+++

found while working ~2RWJ137; same O(WAL) cost as _act had
