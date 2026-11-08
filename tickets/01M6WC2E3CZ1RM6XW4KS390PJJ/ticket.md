+++
id = "01M6WC2E3CZ1RM6XW4KS390PJJ"
title = "portability.md: point udev section and findings at checklist rows 12-16, mention 0403:6001 rules"
type = "task"
category = "done"
outcome = "done"
priority = "medium"
points = 1
reporter = "lognd"
created = "2026-11-08T01:23:53Z"
updated = "2026-11-08T01:24:41Z"
scope = ["docs/portability.md"]

[[acceptance]]
text = "docs/portability.md section 4 states 0403:6001 is present in packaging/udev/99-sadi.rules and labelled UNVERIFIED"
bound = true

[[acceptance]]
text = "docs/portability.md findings item 4 references hardware-verification.md rows 12-16"
bound = true
+++

found while working ~6662Y63; section 4 still says 0403:6001 is not in the rules file, and findings item 4 should link rows 12-16.
