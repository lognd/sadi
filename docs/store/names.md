# Filename sanitiser

Status: current

Owner: ~T5XVYE8. Code: `python/sadi/store/names.py`. Tests: `python/tests/store/test_names.py`.
Rules: [portability.md](../portability.md) section 5; data safety: [data-safety.md](../data-safety.md).

## Contract

`sanitize_name(raw, max_len=64)` maps any text to a single path component that is valid on
Windows, Linux and macOS:

- Allowed characters are `A-Za-z0-9._~-` only. Everything else (the Win32 forbidden set
  `<>:"/\|?*`, control characters, spaces, non-ASCII) becomes `_`.
- No trailing dot; never `.` or `..`.
- Windows device names (`CON PRN AUX NUL COM0-9 LPT0-9`, with or without an extension, any
  case) get a leading `_`.
- Length is at most `max_len` (minimum accepted 24; smaller is a programmer error and raises
  `ValueError`).

A name that is already valid is returned unchanged. Any other name gets a deterministic
`~<10 hex>` suffix (SHA-256 of the raw text), so two different raw inputs do not collapse to
the same output (barring a 40-bit hash collision). The function is idempotent: its output is
valid, hence unchanged by a second pass.

## No overwrite

`unique_name(raw, taken)` returns `Result[str, NameExhausted]`. It compares
case-insensitively (NTFS and default macOS volumes fold case) against `taken` and, on a
clash, appends `~2`, `~3`, ... up to `~9999`. It never returns a name in `taken`; when all
are used the result is `Err(NameExhausted)`. Callers must still create the path exclusively
(`create_exclusive`, `os.mkdir`); this module only chooses names.

Session directories (`<UTC stamp>-<slug>.vNNN`) already carry a timestamp prefix and a
restricted slug, so they are not changed by this ticket.
