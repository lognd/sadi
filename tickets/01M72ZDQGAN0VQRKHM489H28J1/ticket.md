+++
id = "01M72ZDQGAN0VQRKHM489H28J1"
title = "Intermediate export at any step; step rail and panels must not be locked (user feedback)"
type = "story"
category = "todo"
priority = "high"
points = 5
reporter = "lognd"
created = "2026-11-10T14:57:32Z"
updated = "2026-11-10T14:57:32Z"
labels = ["ux"]
scope = ["web/src/components/wizard/**", "web/src/screens/export/**", "python/sadi/server/routes/export.py"]

[[acceptance]]
text = "Export (CSV of captured points so far) is reachable from every wizard step without finishing the phase"
bound = false

[[acceptance]]
text = "Step rail lets the operator view any step read-only without advancing; nothing is locked out of viewing"
bound = false

[[acceptance]]
text = "Intermediate export is labelled PARTIAL in the file and never overwrites a prior export"
bound = false
+++

User: I dont like how everything is barred/uninteractable; I want intermediate exports to look at the data. Audit what is disabled and why; add an Export now action in the shell.
