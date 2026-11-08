"""Dump the FastAPI OpenAPI document deterministically for the committed web client spec."""

# frob:ticket 01M6WTCA5YQJPPTGFH316XQ2DQ

from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from typani import Err, Ok, Result

from sadi.logging_setup import get_logger
from sadi.server.app import AppSettings, create_app

_log = get_logger(__name__)

SPEC_RELPATH = Path("web/src/api/openapi.json")


def render_openapi() -> str:
    """Return the app's OpenAPI document as sorted-key, 2-space JSON with a trailing newline."""
    with TemporaryDirectory() as tmp:
        spec = create_app(AppSettings(data_root=Path(tmp), require_root_lock=False)).openapi()
    return json.dumps(spec, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def write_openapi(dest: Path) -> Result[int, OSError]:
    """Write the rendered spec to dest and return the byte count, or the OS error."""
    text = render_openapi()
    try:
        dest.write_text(text, encoding="utf-8", newline="\n")
    except OSError as exc:
        _log.error("openapi write failed: %s: %s", dest, exc)
        return Err(exc)
    _log.info("openapi written: %s (%d bytes)", dest, len(text))
    return Ok(len(text))


def main(argv: list[str]) -> int:
    """CLI entry: optional single argument is the destination path; returns a process code."""
    dest = Path(argv[0]) if argv else SPEC_RELPATH
    result = write_openapi(dest)
    if isinstance(result, Err):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
