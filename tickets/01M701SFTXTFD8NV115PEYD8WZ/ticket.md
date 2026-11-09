+++
id = "01M701SFTXTFD8NV115PEYD8WZ"
title = "ci: rust windows clippy unused imports and web windows schema.ts CRLF"
type = "chore"
category = "in-progress"
priority = "high"
points = 2
reporter = "lognd"
created = "2026-11-09T11:41:11Z"
updated = "2026-11-09T11:44:30Z"
scope = [".gitattributes", "crates/sadi-proto/tests/serial_loopback.rs", "web/src/api/schema.test.ts"]

[[acceptance]]
text = "clippy -D warnings clean on cfg(unix) and non-unix; vitest schema test passes with CRLF input"
bound = true
+++

crates/sadi-proto/tests/serial_loopback.rs: Duration (line 4) and TransportError (line 9) unused on non-unix because only cfg(unix) tests use them; gate them with cfg(unix). web/src/api/schema.test.ts: Windows checkout gives CRLF in schema.ts so toContain(fresh) fails; add 'web/src/api/schema.ts text eol=lf' (and openapi.json already lf) to .gitattributes and/or normalise CRLF in the test.
