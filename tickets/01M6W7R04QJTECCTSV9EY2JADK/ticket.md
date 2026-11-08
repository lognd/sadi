+++
id = "01M6W7R04QJTECCTSV9EY2JADK"
title = "Data safety: WAL, sessions, snapshots, crash recovery"
type = "epic"
category = "todo"
priority = "high"
parent = "01M6W78507Q819RQ7VXNFZEVFY"
reporter = "lognd"
created = "2026-11-08T00:08:16Z"
updated = "2026-11-08T00:08:16Z"
idempotency_key = "sadi-e_store"
+++

Workstream (non-negotiable): append-only checksummed fsynced WAL before display, O_EXCL versioned sessions, atomic snapshots, derived exports, kill-mid-write tests.

Suggested model: n/a.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001).
