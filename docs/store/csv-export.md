# CSV export line endings

Status: current

Owner: ~K79AJH0. Code: `python/sadi/store/csv_export.py`. Tests: `python/tests/store/test_csv_export.py`.
Policy source: [portability.md](../portability.md) section 8; data safety: [data-safety.md](../data-safety.md).

## Policy

- Encoding UTF-8; row terminator exactly `\r\n` after every row including the last, on
  every OS. Embedded newlines inside quoted cells are kept as written.
- No BOM by default; `excel_bom=True` prefixes `EF BB BF` for Excel with non-ASCII units.
- Bytes are built in memory by `render_csv` and written through a binary fd, so no
  text-mode newline translation can occur on Windows.
- `write_csv_exclusive` creates the file with `O_EXCL`, fsyncs it and its directory, and
  returns `Err(CsvWriteFailure)` if the file exists: an existing file is never rewritten.
- `.gitattributes`: `*.csv -text` (checkout never rewrites fixture bytes) and
  `*.json text eol=lf`; other files `text=auto`.

## Tests

`test_render_bytes_exact_crlf` and `test_file_bytes_match_render` assert the exact bytes;
`test_never_overwrites` the no-overwrite rule; `test_gitattributes_pins_csv_bytes` the rules.
