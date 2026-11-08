+++
id = "01M6WJB330TVRVWW639E6GGFJZ"
title = "Wizard: step completion criteria (e.g. >=1 captured point before complete)"
type = "task"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-08T03:13:28Z"
updated = "2026-11-08T03:19:27Z"
scope = ["python/sadi/core/wizard.py", "python/tests/core/test_wizard.py", "docs/core/wizard.md", "python/sadi/core/lab.py"]
+++

Wizard.complete has no per-step criterion. Add a StepSpec criterion checked in complete(), returning a WizardError hint.
