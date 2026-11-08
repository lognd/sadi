+++
id = "01M6WJB330TVRVWW639E6GGFJZ"
title = "Wizard: step completion criteria (e.g. >=1 captured point before complete)"
type = "task"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-08T03:13:28Z"
updated = "2026-11-08T03:18:35Z"
+++

Wizard.complete has no per-step criterion. Add a StepSpec criterion checked in complete(), returning a WizardError hint.
