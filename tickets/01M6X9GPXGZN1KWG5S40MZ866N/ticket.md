+++
id = "01M6X9GPXGZN1KWG5S40MZ866N"
title = "Enter/Space on a focused button or link triggers the wizard hotkey instead of the control"
type = "bug"
category = "done"
outcome = "done"
priority = "high"
points = 2
reporter = "lognd"
created = "2026-11-08T09:58:29Z"
updated = "2026-11-08T10:00:50Z"
scope = ["web/src/keys/**", "docs/web/wizard.md"]

[[acceptance]]
text = "Enter/Space on a focused button, link, summary or role=button/link activates that control and does not trigger the wizard hotkey; keymap tests cover it"
bound = true
+++

Found while working ~W5XJBZT (usability pass). useKeyCapture only exempts INPUT/TEXTAREA/SELECT, so with Tab focus on a button or link, Enter resolves to 'primary' (complete step) and Space to 'accept', both preventDefault'd: the focused control never activates. Repro: LVDT step, Tab to 'Mark load change', Enter -> the step completes with no points. Same for Skip this step, Download link, Edit/Exclude buttons on Review. Fix: in useKeyCapture/resolveKey return null for Enter/Space when the target is a button, link, summary or role=button/link; add keymap tests; extend e2e to activate controls via Tab+Enter.
