+++
id = "01M71KE93DMK963M32SPH83NF4"
title = "GP weight panel: recommended load, gain, alternatives, confidence, stop-early"
type = "task"
category = "todo"
priority = "high"
points = 5
reporter = "lognd"
created = "2026-11-10T02:08:53Z"
updated = "2026-11-10T02:08:53Z"
labels = ["model:sonnet"]
scope = ["web/src/components/guidance/**", "web/src/api/schema.ts"]

[[links]]
kind = "blocked-by"
target = "01M71KCTETKE1AE0GZ35MQ11EV"

[[acceptance]]
text = "GuidancePanel shows the GP-recommended next load (kg and N), expected gain, up to 3 alternatives as one-click fill buttons, a confidence meter, and the advisory stop-early note, using the new GuidanceState fields"
bound = false

[[acceptance]]
text = "Panel degrades gracefully when GP fields are absent (even-schedule fallback text); vitest component tests cover both"
bound = false
+++

Frontend half of the GP weight selection. Blocked by the GpLoadSuggester ticket. ASCII only, no Co-Authored-By line.
