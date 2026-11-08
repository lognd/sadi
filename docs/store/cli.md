# `sadi store` command line

Status: current

Owner: ~D2M701Q. Code: `python/sadi/cli/store.py`. Tests: `python/tests/cli/test_store_cli.py`.
Design: [data-safety.md](../data-safety.md) section 5; sessions: [session.md](session.md);
CSV rules: [csv-export.md](csv-export.md).

Run with `python -m sadi.cli.store <command>` or the `sadi-store` script.

| Command | Effect |
|---|---|
| `list ROOT` | One line per session under `ROOT/sessions`: status, record count, last seq. Read-only. |
| `verify SESSION` | Checks every record CRC and every segment seal; prints one line per segment. Read-only. |
| `recover SESSION` | Opens a NEW version (`.vNNN+1`) continuing from the verified part. The old directory is never modified. |
| `export SESSION OUT.csv [--excel-bom]` | Writes verified records (seq, wall_ns, type, payload) through `write_csv_exclusive`. An existing `OUT.csv` is refused. |

Payloads of JSON records are written as text, binary payloads as hex.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success; for `verify`, everything checked is intact. |
| 1 | `verify`: readable but needs attention (torn tail kept in place, no WAL, or live writer). |
| 2 | Bad command-line arguments. |
| 3 | The WAL is damaged mid-log; `recover` and `export` refuse, nothing was changed. |
| 4 | Not a session directory, no WAL, or an OS error. |
| 5 | Refused to overwrite an existing export target or to touch a session in use. |

A torn tail (unverified bytes after the last good record) is reported but never truncated.
