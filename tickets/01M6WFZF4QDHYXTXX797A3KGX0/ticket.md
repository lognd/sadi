+++
id = "01M6WFZF4QDHYXTXX797A3KGX0"
title = "Doctor checks for plugin state with step-by-step fixes"
type = "task"
category = "in-progress"
priority = "high"
points = 3
parent = "01M6WFY7CGXVKS192DN0WXNCH9"
reporter = "lognd"
created = "2026-11-08T02:32:10Z"
updated = "2026-11-08T02:55:19Z"
labels = ["plugins", "creates:python/sadi/plugins/doctor.py", "creates:python/tests/plugins/test_doctor.py"]
scope = ["python/sadi/plugins/doctor.py", "python/tests/plugins/test_doctor.py"]

[[links]]
kind = "blocked-by"
target = "01M6WFYN8C6YH5D79CPEKSP69P"

[[links]]
kind = "blocked-by"
target = "01M6WFZ1R6ATYWRVW3315G6CCX"

[[acceptance]]
text = "Each failure state in PluginRecord maps to a finding with >=2 fix steps"
bound = true

[[acceptance]]
text = "Healthy registry yields zero findings"
bound = true

[[acceptance]]
text = "Function never raises on a failed record"
bound = true
+++

check_plugins(registry) -> list[DoctorFinding] (pydantic: plugin id, severity, code, message, fixes: ordered list of numbered step strings). Findings: load error (with traceback summary and 'run sadi plugins info <id>'), api_version mismatch (installed vs required range; upgrade or pin steps), unmet requires, duplicate id, disabled plugin (sadi plugins enable <id>), local dir unreadable, session references a plugin that is missing (consumes SessionPluginRef list; interface only, wiring in provenance ticket). Pure function over registry data; never imports plugin code itself. Docs for doctor.md are done in the docs ticket.
