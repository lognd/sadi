+++
id = "01M6W7RB7ZFKF3DVKWW74FQXWT"
title = "Run screens: calibrate, tare, elastic, plastic capture screens with live view"
type = "task"
category = "in-progress"
priority = "high"
points = 8
parent = "01M6W7R0BA45XYP4MGXJ21Z778"
reporter = "lognd"
created = "2026-11-08T00:08:28Z"
updated = "2026-11-08T06:14:31Z"
idempotency_key = "sadi-f11"
labels = ["ws:web", "model:sonnet", "creates:web/src/screens/run/**", "creates:docs/web/run-screens.md"]
scope = ["web/src/screens/run/**", "docs/web/run-screens.md", "docs/index.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R3D3KT3NM6JETDDAPA9P"

[[links]]
kind = "blocked-by"
target = "01M6W7R3EPVRGG4R93B7WJVKMW"

[[links]]
kind = "blocked-by"
target = "01M6W7R3KN3HXVMJQ1D3MJNBZY"

[[links]]
kind = "blocked-by"
target = "01M6W7R3TJETR6N3EVA9PMPWH8"

[[links]]
kind = "blocked-by"
target = "01M6W7R41EVGYTSV1B72ZQVKAB"

[[links]]
kind = "blocked-by"
target = "01M6W7RAH93KKNK1WH67KWS2S7"

[[links]]
kind = "blocked-by"
target = "01M6W7RAPKVH796SZ6Z9EFDXQE"

[[links]]
kind = "blocked-by"
target = "01M6W7RB0GPGHTABW7P4XEGRNJ"

[[acceptance]]
text = "Live screen per F0B: big readouts, trace, settle/creep indicator, live plot of the phase (calibration fit, stress-strain), capture via accept key, forced-early confirmation"
bound = true

[[acceptance]]
text = "Saturation warning visible and in status bar; disconnect behaviour per design"
bound = true

[[acceptance]]
text = "Works end-to-end in sim mode"
bound = true
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). TypeScript: strict mode, no any, ESLint + vitest clean.
