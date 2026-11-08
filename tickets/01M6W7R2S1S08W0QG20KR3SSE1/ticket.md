+++
id = "01M6W7R2S1S08W0QG20KR3SSE1"
title = "Live-view UX design: readouts, trace, indicators, stress-strain, guidance placement"
type = "docs"
category = "done"
outcome = "done"
priority = "high"
points = 5
parent = "01M6W7R0BA45XYP4MGXJ21Z778"
reporter = "lognd"
created = "2026-11-08T00:08:19Z"
updated = "2026-11-08T02:04:31Z"
idempotency_key = "sadi-f0b"
labels = ["ws:web", "design", "model:fable", "creates:docs/live-view.md"]
scope = ["docs/live-view.md", "docs/ux.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R1PV3YSB3EKX6K80WDK8"

[[links]]
kind = "blocked-by"
target = "01M6W7R23Q44RD6WVCBGKVPN2E"

[[acceptance]]
text = "ASCII layout of the live screen: big readouts (V, height, load, strain, stress), scrolling trace, settle/creep indicator, saturation light, live stress-strain with E fit, next-step panel, confidence meter"
bound = true

[[acceptance]]
text = "Defines update rates, decimation, what is shown while creeping vs settled, colour/shape coding that works in screenshots and colour-blind safe, behaviour on disconnect"
bound = true

[[acceptance]]
text = "Specifies each plot's annotation content (titles, axis labels with units, legends, CI bands, fit equation text) consumed by F3-F7"
bound = true

[[acceptance]]
text = "Specifies stale-number marker, MC/GP refinement progress indicator, and the uncertainty-budget panel (dominant input) and formula/derivation view placement"
bound = true
+++

Suggested model: Fable.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001).
