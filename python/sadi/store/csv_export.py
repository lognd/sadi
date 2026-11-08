"""Byte-exact CSV export: UTF-8, CRLF row terminator, identical on every OS (portability section 8).

`render_csv` builds the bytes in memory (no text-mode file, so no newline translation is
possible); `write_csv_exclusive` writes them to a new file only, never overwriting one.
"""

# frob:ticket 01M6WA538CKP1CX6Q11K79AJH0
from __future__ import annotations

import csv
import io
import os
from collections.abc import Iterable, Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict
from typani import Err, Ok, Result

from sadi.logging_setup import get_logger
from sadi.store.durable import DurableError, create_exclusive, fsync_dir, fsync_file

_log = get_logger(__name__)

CSV_EOL = "\r\n"
UTF8_BOM = b"\xef\xbb\xbf"
Cell = str | int | float


class CsvWriteFailure(BaseModel):
    """The CSV file could not be created or written; `cause` is the durable-layer error."""

    model_config = ConfigDict(frozen=True)

    path: Path
    cause: DurableError | None = None
    detail: str = ""


def render_csv(
    header: Sequence[str], rows: Iterable[Sequence[Cell]], *, excel_bom: bool = False
) -> bytes:
    """Return the CSV bytes: UTF-8, CRLF after every row (including the last), optional BOM."""
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator=CSV_EOL)
    writer.writerow(header)
    count = 0
    for row in rows:
        writer.writerow(row)
        count += 1
    data = buf.getvalue().encode("utf-8")
    _log.debug("rendered csv: %d rows, %d bytes, bom=%s", count, len(data), excel_bom)
    return UTF8_BOM + data if excel_bom else data


def write_csv_exclusive(
    path: Path,
    header: Sequence[str],
    rows: Iterable[Sequence[Cell]],
    *,
    excel_bom: bool = False,
) -> Result[int, CsvWriteFailure]:
    """Write a CSV to a NEW file (O_EXCL) and fsync it; return bytes written, never overwrite."""
    data = render_csv(header, rows, excel_bom=excel_bom)
    created = create_exclusive(path)
    if created.is_err:
        _log.error("csv export refused for %s: %s", path, created.unwrap_err())
        return Err(CsvWriteFailure(path=path, cause=created.unwrap_err()))
    fd = created.unwrap()
    try:
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view) :]
        synced = fsync_file(fd)
    except OSError as exc:
        _log.error("csv write failed for %s: %s", path, exc)
        return Err(CsvWriteFailure(path=path, detail=str(exc)))
    finally:
        os.close(fd)
    if synced.is_err:
        return Err(CsvWriteFailure(path=path, cause=synced.unwrap_err()))
    fsync_dir(path.parent)
    _log.info("csv export written: %s (%d bytes)", path, len(data))
    return Ok(len(data))
