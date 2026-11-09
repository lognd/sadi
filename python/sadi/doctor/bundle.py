"""`sadi doctor --bundle`: write a redacted diagnostics zip to a NEW path, never replacing a file."""

# frob:ticket 01M6WA9WYE9D71BBA7AV3H5CGF
from __future__ import annotations

import io
import json
import logging
import os
import re
import uuid
import zipfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from typani import Err, Ok, Result, propagate

from sadi.doctor.schema import DoctorError, DoctorReport
from sadi.logging_setup import get_logger
from sadi.store.durable import create_exclusive, fsync_dir, fsync_file, rename_noreplace

_log = get_logger(__name__)

BUNDLE_FORMAT = 1
LOG_TAIL_LINES = 500
_SECRET = re.compile(
    r"(?i)(api[_-]?key|token|passw(?:or)?d|secret|authorization|bearer|credential|\.env)"
)

__all__ = ["LogCapture", "capture_log", "redact", "write_bundle"]


class LogCapture(logging.Handler):
    """Keep the last LOG_TAIL_LINES formatted records of the run for the bundle."""

    def __init__(self) -> None:
        """Start empty."""
        super().__init__(logging.DEBUG)
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        """Remember one record, dropping the oldest beyond the cap."""
        self.lines.append(f"{record.levelname} {record.name}: {record.getMessage()}")
        del self.lines[:-LOG_TAIL_LINES]


@contextmanager
def capture_log() -> Generator[LogCapture]:
    """Attach a LogCapture to the `sadi` logger for the duration of the block."""
    handler = LogCapture()
    logger = logging.getLogger("sadi")
    logger.addHandler(handler)
    try:
        yield handler
    finally:
        logger.removeHandler(handler)


def redact(text: str, home: str | None = None) -> str:
    """Mask secret-looking lines and the home directory so a bundle is safe to share."""
    home = home if home is not None else str(Path.home())
    out = []
    for line in text.splitlines():
        out.append("[redacted line]" if _SECRET.search(line) else line)
    joined = "\n".join(out)
    return joined.replace(home, "~") if home and home != "/" else joined


def _inside(path: Path, root: Path) -> bool:
    """True when `path` resolves to `root` or below it."""
    resolved = path.resolve()
    base = root.resolve()
    return resolved == base or base in resolved.parents


def _payload(report: DoctorReport, log_lines: list[str]) -> bytes:
    """Build the zip bytes: report.json, log_tail.txt and meta.json; no environment, no .env."""
    from sadi.doctor.cli import catalog_markdown

    catalog = catalog_markdown()
    meta = {
        "bundle_format": BUNDLE_FORMAT,
        "run_id": str(report.run_id),
        "doctor_checks_sha": __import__("hashlib").sha256(catalog.encode()).hexdigest()[:16],
        "sadi_version": report.host.sadi_version,
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("report.json", redact(report.model_dump_json(indent=2)))
        z.writestr("log_tail.txt", redact("\n".join(log_lines)) + "\n")
        z.writestr("meta.json", json.dumps(meta, indent=2) + "\n")
    return buf.getvalue()


@propagate
def _write_tmp(tmp: Path, data: bytes) -> Result[None, DoctorError]:
    """Create `tmp` exclusively, write all bytes and fsync."""
    created = create_exclusive(tmp)
    if created.is_err:
        _log.error("bundle tmp create failed: %s", created.unwrap_err())
        return Err(DoctorError.BundleWriteFailed)
    fd = created.unwrap()
    try:
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view) :]
        synced = fsync_file(fd)
    except OSError as exc:
        _log.error("bundle write failed: %s", exc)
        return Err(DoctorError.BundleWriteFailed)
    finally:
        os.close(fd)
    synced.unwrap(err=DoctorError.BundleWriteFailed)
    return Ok(None)


def write_bundle(
    report: DoctorReport, log_lines: list[str], dest: Path, data_root: Path
) -> Result[Path, DoctorError]:
    """Write the bundle to `dest` (tmp, fsync, no-replace rename); refuse existing or in-data-root."""
    if dest.exists() or dest.is_symlink():
        _log.error("bundle refused: %s exists", dest)
        return Err(DoctorError.BundleExists)
    if _inside(dest, data_root):
        _log.error("bundle refused: %s is inside the data root", dest)
        return Err(DoctorError.BundleInsideDataRoot)
    tmp = dest.with_name(f"{dest.name}.tmp-{uuid.uuid4().hex[:8]}")
    written = _write_tmp(tmp, _payload(report, log_lines))
    if isinstance(written, Ok):
        renamed = rename_noreplace(tmp, dest)
        if renamed.is_ok:
            fsync_dir(dest.parent)
            _log.info("bundle written: %s", dest)
            return Ok(dest)
        _log.error("bundle rename failed: %s", renamed.unwrap_err())
        tmp.unlink(missing_ok=True)
        return Err[Path, DoctorError](
            DoctorError.BundleExists if dest.exists() else DoctorError.BundleWriteFailed
        )
    tmp.unlink(missing_ok=True)
    return Err[Path, DoctorError](written.unwrap_err())
