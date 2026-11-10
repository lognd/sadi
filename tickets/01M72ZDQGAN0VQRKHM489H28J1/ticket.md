+++
id = "01M72ZDQGAN0VQRKHM489H28J1"
title = "Intermediate export at any step; step rail and panels must not be locked (user feedback)"
type = "story"
category = "in-progress"
priority = "high"
points = 5
reporter = "lognd"
created = "2026-11-10T14:57:32Z"
updated = "2026-11-10T15:04:56Z"
labels = ["ux"]
scope = ["web/src/components/wizard/**", "web/src/screens/export/**", "python/sadi/server/routes/export.py", "python/sadi/labs/lctt/export_csv.py", "python/sadi/labs/lctt/lab.py", "docs/lctt/export-csv.md"]

[[acceptance]]
text = "Export (CSV of captured points so far) is reachable from every wizard step without finishing the phase"
bound = false

[[acceptance]]
text = "Step rail lets the operator view any step read-only without advancing; nothing is locked out of viewing"
bound = false

[[acceptance]]
text = "Intermediate export is labelled PARTIAL in the file and never overwrites a prior export"
bound = false

[[acceptance]]
text = "Partial export works with calibration points only (no tare/load yet): build_document must not refuse; header carries cal points, fit, n, r2"
bound = false

[[acceptance]]
text = "Standalone calibration CSV (volts, height, fit slope/intercept/se/t95/U95) downloadable mid-run, matching LabVIEW lctt_export_calibration.vi"
bound = false

[[acceptance]]
text = "Every export is served from the open session without stopping the run or closing the VI-equivalent session"
bound = false
+++

User: I dont like how everything is barred/uninteractable; I want intermediate exports to look at the data. Audit what is disabled and why; add an Export now action in the shell.
