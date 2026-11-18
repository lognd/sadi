Snapshots now store NOTE payloads so a rebase skips the whole-WAL note walk, and stale replay-cache entries re-verify on a background thread instead of the request path.
