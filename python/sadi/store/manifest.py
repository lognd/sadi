"""Session manifest cache (data-safety 8.4): frozen pydantic model and atomic-replace writer."""

# frob:ticket 01M6W7R1VQHABR51SH64668M06
# frob:ticket 01M6WFZFBK0KYAGBM1CD5GGH60
from __future__ import annotations

import os
import secrets
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError
from typani import Err, Ok, Result, propagate

from sadi.logging_setup import get_logger
from sadi.store.durable import DurableError, DurableIo, atomic_replace, create_exclusive, fsync_file
from sadi.store.failpoints import failpoint

_log = get_logger(__name__)

MANIFEST_NAME = "manifest.json"
MANIFEST_VERSION = 1

SessionState = Literal[
    "open", "closed", "crashed", "corrupt", "incomplete"
]  # frob:ticket 01M729648PC6N7FK6D2J6H1ETV


class SessionPluginRef(BaseModel):
    """Provenance: id and version of a plugin that was active when a session version was made."""

    model_config = ConfigDict(frozen=True)
    id: str
    version: str


class PluginWarning(BaseModel):
    """Non-fatal reopen finding: a recorded plugin is missing or at a different version."""

    model_config = ConfigDict(frozen=True)
    plugin_id: str
    recorded_version: str
    found_version: str | None
    message: str


def plugin_warnings(
    recorded: Sequence[SessionPluginRef], available: Mapping[str, str]
) -> tuple[PluginWarning, ...]:
    """Warn for recorded refs missing from, or differing in, `available` (id -> version)."""
    out: list[PluginWarning] = []
    for ref in recorded:
        found = available.get(ref.id)
        if found is None:
            msg = f"plugin '{ref.id}' {ref.version} used by this session is not available"
        elif found != ref.version:
            msg = f"plugin '{ref.id}' version differs: session used {ref.version}, found {found}"
        else:
            continue
        _log.warning("session provenance: %s", msg)
        out.append(
            PluginWarning(
                plugin_id=ref.id, recorded_version=ref.version, found_version=found, message=msg
            )
        )
    return tuple(out)


class Manifest(BaseModel):
    """Derived, losable description of one session version (never primary data, invariant I7)."""

    model_config = ConfigDict(frozen=True)
    v: int = MANIFEST_VERSION
    format_version: int = 1
    session_uuid: str
    dir_name: str
    family: str
    version: int
    parent: str | None = None
    parent_last_seq: int | None = None
    created: datetime
    lab_module: str = ""
    specimen: dict[str, str] = {}
    state: SessionState = "open"
    closed: datetime | None = None
    last_seq: int | None = None
    # Optional, backward compatible: absent in old manifests (defaults to empty).
    plugins: tuple[SessionPluginRef, ...] = ()
    # frob:ticket 01M71SYG3H3X7GJT21TE6MY8YC
    # Derived mirror of the SYNTHETIC marker file; the marker, not this flag, is authoritative.
    synthetic: bool = False
    # frob:ticket 01M72D2TZS82YV31D8FPXPD3AB
    # Set only by spill import: "joined" (self-contained successor) or "fragment" (spill alone).
    spill_import: str | None = None
    # frob:ticket 01M72TJ0CQPCRKAW2EWSFP9Y8Z
    # True when the data's origin was lost (orphan spill import): neither real nor synthetic.
    provenance_unknown: bool = False


class ManifestInvalid(BaseModel):
    """manifest.json exists but is unreadable or fails validation; the file is left untouched."""

    model_config = ConfigDict(frozen=True)
    path: Path
    reason: str
    hint: str = "The manifest is only a cache; it is regenerated when the session is resumed."


def read_manifest(session_dir: Path) -> Result[Manifest | None, ManifestInvalid]:
    """Read manifest.json without side effects; Ok(None) when it does not exist."""
    path = session_dir / MANIFEST_NAME
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        _log.debug("no manifest at %s", path)
        return Ok(None)
    except OSError as exc:
        _log.error("cannot read manifest %s: %s", path, exc)
        return Err(ManifestInvalid(path=path, reason=str(exc)))
    try:
        return Ok(Manifest.model_validate_json(raw))
    except ValidationError as exc:
        _log.error("invalid manifest %s: %s", path, exc)
        return Err(ManifestInvalid(path=path, reason=str(exc)))


@propagate
def write_manifest(session_dir: Path, manifest: Manifest) -> Result[None, DurableError]:
    """Atomically write manifest.json via an exclusive same-directory tmp file and replace."""
    dst = session_dir / MANIFEST_NAME
    tmp = session_dir / f"{MANIFEST_NAME}.tmp-{os.getpid()}-{secrets.token_hex(4)}"
    created = create_exclusive(tmp)
    fd = created.unwrap()
    data = manifest.model_dump_json(indent=2).encode("ascii") + b"\n"
    try:
        try:
            failpoint("session.manifest.write")
            os.write(fd, data)
        except OSError as exc:
            _log.error("manifest tmp write %s failed: %s", tmp, exc)
            return Err(DurableIo(errno=exc.errno or 5, path=tmp))
        synced = fsync_file(fd)
    finally:
        os.close(fd)
    if synced.is_err:
        return synced
    try:
        failpoint("session.manifest.before_replace")
    except OSError as exc:
        _log.error("manifest replace aborted for %s: %s", dst, exc)
        return Err(DurableIo(errno=exc.errno or 5, path=dst))
    replaced = atomic_replace(tmp, dst)
    if replaced.is_ok:
        _log.info("manifest written: %s state=%s", dst, manifest.state)
    return replaced
