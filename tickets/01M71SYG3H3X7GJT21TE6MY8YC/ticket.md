+++
id = "01M71SYG3H3X7GJT21TE6MY8YC"
title = "Synthetic 32 AWG copper specimen source, loudly labelled, opt-in only"
type = "story"
category = "in-progress"
priority = "medium"
points = 8
reporter = "lognd"
created = "2026-11-10T04:02:36Z"
updated = "2026-11-10T04:31:05Z"
scope = ["python/sadi/**", "python/tests/**", "docs/synthetic.md", "docs/index.md", "web/src/api/**"]

[[acceptance]]
text = "Synthetic source generates 32 AWG Cu stress/strain-correlated LVDT and load volts with elastic region, yield, strain hardening, creep under hold, and seeded noise; deterministic for a seed"
bound = true

[[acceptance]]
text = "Enabling it needs an explicit flag AND a typed confirmation phrase; never default, never via env alone; sessions and every export/plot/results payload carry synthetic=true provenance that cannot be dropped, and real data is never mixed or overwritten"
bound = false

[[acceptance]]
text = "Tests prove provenance propagates to session store, export, and API, that fitted E and yield land in a plausible Cu range, and that the real-device path is unaffected"
bound = false

[[acceptance]]
text = "docs/synthetic.md documents usage, physics model and safeguards"
bound = false
+++
