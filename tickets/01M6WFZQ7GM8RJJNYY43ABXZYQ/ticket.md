+++
id = "01M6WFZQ7GM8RJJNYY43ABXZYQ"
title = "Plugin docs: plugins.md, lab-modules, doctor, CLI, index"
type = "docs"
category = "in-progress"
priority = "medium"
points = 2
parent = "01M6WFY7CGXVKS192DN0WXNCH9"
reporter = "lognd"
created = "2026-11-08T02:32:18Z"
updated = "2026-11-08T02:58:43Z"
labels = ["plugins"]
scope = ["docs/plugins.md", "docs/core/lab-modules.md", "docs/doctor.md", "docs/index.md", "docs/data-safety.md"]

[[links]]
kind = "blocked-by"
target = "01M6WFZ1N70HDJJRZWRHWP4E7Y"

[[links]]
kind = "blocked-by"
target = "01M6WFZ1R6ATYWRVW3315G6CCX"

[[links]]
kind = "blocked-by"
target = "01M6WFZF4QDHYXTXX797A3KGX0"

[[links]]
kind = "blocked-by"
target = "01M6WFZF75SH31V398E8P7WC5Y"

[[links]]
kind = "blocked-by"
target = "01M6WFZF9FD9QNXP62MCETRNEA"

[[links]]
kind = "blocked-by"
target = "01M6WFZFBK0KYAGBM1CD5GGH60"

[[acceptance]]
text = "Docs match shipped signatures"
bound = true

[[acceptance]]
text = "No mention of private project contents in tracked docs"
bound = true

[[acceptance]]
text = "frob check --ticket passes (no doc drift)"
bound = true
+++

Update docs/plugins.md (drafted as design) to final signatures; lab-modules.md now describes labs as a plugin contribution kind and drops the 'not a plugin system' claim; doctor.md gets the plugin checks and fix steps; document SADI_PLUGIN_PATH, sadi plugins CLI, endpoint, session provenance, how to write a local plugin. Run frob doc ack as needed. Avoid collisions with the course-scrub ticket ~XKS8M68: start after it lands.
