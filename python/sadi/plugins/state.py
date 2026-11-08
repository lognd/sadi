"""Persisted plugin enable/disable state: a small atomic JSON file in the user config dir."""

# frob:ticket 01M6WFZF75SH31V398E8P7WC5Y

from __future__ import annotations

import contextlib
import json
import os
import tempfile
import time
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError
from typani import Err, ErrorSet, Ok, Result

from sadi.logging_setup import get_logger

_log = get_logger(__name__)

STATE_FILENAME = "plugins.json"
"""Name of the state file inside the config dir."""


class PluginStateError(ErrorSet):
    """Failure modes of reading and writing the plugin state file."""

    Unreadable = "Plugin state file could not be read; check its permissions"
    Corrupt = "Plugin state file is damaged; it was kept aside as the note says, then retry"
    WriteFailed = "Plugin state file could not be written; check the config dir is writable"


class PluginStateFile(BaseModel):
    """On-disk schema: format version and the sorted ids of disabled plugins."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: int = 1
    disabled: tuple[str, ...] = ()


def state_path(config_dir: Path) -> Path:
    """Return the state file path under `config_dir`."""
    return config_dir / STATE_FILENAME


def load_disabled(config_dir: Path) -> Result[frozenset[str], PluginStateError]:
    """Read the disabled ids; a missing file means none, a damaged one is left untouched."""
    path = state_path(config_dir)
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return Ok(frozenset())
    except OSError as exc:
        _log.error("cannot read %s: %s", path, exc)
        return Err[frozenset[str], PluginStateError](PluginStateError.Unreadable).note(
            f"{path}: {exc}"
        )
    try:
        parsed = PluginStateFile.model_validate(json.loads(raw))
    except (ValueError, ValidationError) as exc:
        _log.error("plugin state %s is corrupt: %s", path, exc)
        return Err[frozenset[str], PluginStateError](PluginStateError.Corrupt).note(
            f"{path}: {exc}"
        )
    return Ok(frozenset(parsed.disabled))


def _keep_aside(path: Path) -> Path | None:
    """Rename a damaged state file to a unique `.corrupt-<ns>` sibling; None if it is gone."""
    aside = path.with_name(f"{path.name}.corrupt-{time.time_ns()}")
    try:
        os.replace(path, aside)
    except OSError as exc:
        _log.error("cannot move %s aside: %s", path, exc)
        return None
    _log.warning("kept damaged plugin state as %s", aside)
    return aside


def _atomic_write(path: Path, text: str) -> None:
    """Write `text` to `path` via temp file, fsync and rename; raises OSError on failure."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise
    with contextlib.suppress(OSError):  # directory fsync is best effort (not on Windows)
        dir_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)


def set_enabled(
    config_dir: Path, plugin_id: str, enabled: bool
) -> Result[frozenset[str], PluginStateError]:
    """Persist plugin `plugin_id` as enabled/disabled; a corrupt file is moved aside, not replaced.

    On a corrupt file nothing is written: the file is renamed aside and Corrupt is returned
    naming the new path, so no data is lost and a retry starts clean.
    """
    current = load_disabled(config_dir)
    if current.is_err:
        err = current.danger_err
        if err is PluginStateError.Corrupt:
            aside = _keep_aside(state_path(config_dir))
            where = f"kept as {aside}" if aside else "could not be moved aside"
            return Err[frozenset[str], PluginStateError](err).note(
                f"{state_path(config_dir)} {where}"
            )
        return Err(err)
    disabled = set(current.danger_ok)
    disabled.discard(plugin_id) if enabled else disabled.add(plugin_id)
    body = PluginStateFile(disabled=tuple(sorted(disabled)))
    try:
        _atomic_write(state_path(config_dir), body.model_dump_json(indent=2) + "\n")
    except OSError as exc:
        _log.error("cannot write plugin state: %s", exc)
        return Err[frozenset[str], PluginStateError](PluginStateError.WriteFailed).note(
            f"{state_path(config_dir)}: {exc}"
        )
    _log.info("plugin %s %s", plugin_id, "enabled" if enabled else "disabled")
    return Ok(frozenset(disabled))
