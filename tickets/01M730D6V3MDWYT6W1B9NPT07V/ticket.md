+++
id = "01M730D6V3MDWYT6W1B9NPT07V"
title = "Read-only step view should render the step's data panels, not hide them behind a banner"
type = "bug"
category = "todo"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-10T15:14:44Z"
updated = "2026-11-10T15:14:44Z"
scope = ["web/src/components/wizard/**"]

[[links]]
kind = "blocked-by"
target = "01M72XJMDHV60KRBV1ANWKHKC9"

[[acceptance]]
text = "Opening a past step from the step rail shows that step's data panels read-only (no capture controls)"
bound = false
+++

Follow-up from ~89H28J1: the read-only view hides content behind a banner.
