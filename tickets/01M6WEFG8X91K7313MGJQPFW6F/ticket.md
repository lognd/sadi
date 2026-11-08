+++
id = "01M6WEFG8X91K7313MGJQPFW6F"
title = "store: import emergency spill files as a new session version at startup"
type = "task"
category = "done"
outcome = "done"
priority = "high"
points = 5
parent = "01M6W7R04QJTECCTSV9EY2JADK"
reporter = "lognd"
created = "2026-11-08T02:05:58Z"
updated = "2026-11-08T02:10:15Z"
idempotency_key = "sadi-store-spill-import"
labels = ["creates:python/sadi/store/spill.py", "creates:python/tests/store/test_spill.py", "creates:docs/store/spill.md"]
scope = ["python/sadi/store/spill.py", "python/tests/store/test_spill.py", "docs/store/spill.md", "docs/store/session.md", "docs/README.md", "changelog.d/01M6WEFG8X91K7313MGJQPFW6F.changed.md"]

[[acceptance]]
text = "On start, spill files under <data-root>/spill, the user data dir and the OS temp dir are discovered and validated with the WAL framing and checksums"
bound = true

[[acceptance]]
text = "A valid spill is imported as a new version dir, never overwriting; the original spill file is kept, not deleted"
bound = true

[[acceptance]]
text = "A corrupt or partial spill imports its valid prefix and reports the rest; recovery never truncates"
bound = true
+++
