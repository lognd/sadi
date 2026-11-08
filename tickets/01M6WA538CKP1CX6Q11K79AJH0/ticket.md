+++
id = "01M6WA538CKP1CX6Q11K79AJH0"
title = "CSV export eol policy: .gitattributes text/eol rules + CRLF byte test"
type = "task"
category = "done"
outcome = "done"
priority = "low"
points = 2
reporter = "lognd"
created = "2026-11-08T00:50:23Z"
updated = "2026-11-08T01:23:53Z"
scope = ["python/sadi/store/csv_export.py", "python/tests/store/test_csv_export.py", "docs/store/csv-export.md", "docs/portability.md", "docs/README.md", ".gitattributes", "changelog.d/01M6WA538CKP1CX6Q11K79AJH0.added.md"]

[[acceptance]]
text = "CSV export bytes are identical on every OS: UTF-8, CRLF row terminator, no BOM by default, proven by a byte-level test"
bound = true

[[acceptance]]
text = "Export never overwrites an existing file (exclusive create)"
bound = true

[[acceptance]]
text = ".gitattributes pins eol for CSV fixtures (-text) and JSON (eol=lf), documented in portability.md"
bound = true
+++
