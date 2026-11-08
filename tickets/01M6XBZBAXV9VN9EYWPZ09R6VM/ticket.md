+++
id = "01M6XBZBAXV9VN9EYWPZ09R6VM"
title = "Investigate DOC001/COV001 parse holes in 7 python files"
type = "chore"
category = "in-progress"
priority = "low"
points = 2
reporter = "lognd"
created = "2026-11-08T10:41:26Z"
updated = "2026-11-08T10:41:26Z"

[[acceptance]]
text = "Identify the syntax causing parse holes in python/sadi/core/device.py, jobs/{manager,pool,state,testing}.py, tests/store/test_lock.py, tools/check_typani_collisions.py; remove them with idiomatic rewrites or document the frob limitation in docs; frob check shows no partial-parse note"
bound = false
+++
