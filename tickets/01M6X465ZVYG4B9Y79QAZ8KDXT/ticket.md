+++
id = "01M6X465ZVYG4B9Y79QAZ8KDXT"
title = "curve_source and notes() still walk the whole WAL per request"
type = "bug"
category = "todo"
priority = "medium"
reporter = "lognd"
created = "2026-11-08T08:25:21Z"
updated = "2026-11-08T08:25:21Z"
+++

found while working ~2RWJ137; same O(WAL) cost as _act had
