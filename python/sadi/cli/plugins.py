"""`sadi plugins`: list, inspect, enable and disable plugins.

Enable/disable is persisted in the user config dir (sadi.plugins.state) and takes effect on
the next start. Exit codes are the `Exit` constants below; failures print one plain line.
"""

# frob:ticket 01M6WFZF75SH31V398E8P7WC5Y
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict
from typani import Err, Ok, Result

from sadi.logging_setup import get_logger
from sadi.plugins.builtin import builtin_source
from sadi.plugins.local import LocalDirSource
from sadi.plugins.registry import PluginRecord, PluginRegistry
from sadi.plugins.settings import PluginSettings
from sadi.plugins.sources import EntryPointSource, PluginSource
from sadi.plugins.state import PluginStateError, load_disabled, set_enabled

_log = get_logger(__name__)

SourceFactory = Callable[[PluginSettings], Sequence[PluginSource]]
"""Builds the plugin sources for given settings (injectable for tests)."""

RESTART_NOTE = "Takes effect the next time SADI starts."


class Exit:
    """Documented process exit codes."""

    OK = 0
    UNKNOWN_PLUGIN = 2  # also argparse's usage code: the id (or arguments) were not understood
    STATE = 3  # the enable/disable state file could not be read or written


class CliFailure(BaseModel):
    """A command outcome that is not success: a plain-language message and an exit code."""

    model_config = ConfigDict(frozen=True)
    message: str
    code: int


def _out(text: str = "") -> None:
    """Write one line of intended CLI output to stdout."""
    sys.stdout.write(text + "\n")


def _err(text: str) -> None:
    """Write one line of CLI error output to stderr."""
    sys.stderr.write(text + "\n")


def default_sources(settings: PluginSettings) -> list[PluginSource]:
    """Return the standard source stack: built-in, entry points, local dirs."""
    return [builtin_source(), EntryPointSource(), LocalDirSource(settings=settings)]


def _state_failure(err: Err[object, PluginStateError]) -> CliFailure:
    """Render a state-file error as a CliFailure including its notes."""
    detail = "; ".join(err.notes)
    return CliFailure(message=f"{err.error.description} ({detail})", code=Exit.STATE)


def _discover(settings: PluginSettings, sources: SourceFactory | None) -> PluginRegistry:
    """Discover plugins honouring the persisted disabled set; a bad state file only warns."""
    loaded = load_disabled(settings.config_dir)
    disabled: frozenset[str] = frozenset()
    if isinstance(loaded, Ok):
        disabled = loaded.value
    else:
        _err(f"warning: {_state_failure(loaded).message}; treating all plugins as enabled")
    return PluginRegistry.discover((sources or default_sources)(settings), disabled)


def _row(rec: PluginRecord) -> dict[str, object]:
    """JSON-safe summary of one record."""
    return {
        "id": rec.id,
        "version": rec.manifest.version if rec.manifest else None,
        "source": rec.source,
        "state": rec.state.value,
        "errors": [f"{i.kind.name}: {i.note}" if i.note else i.kind.name for i in rec.errors],
    }


def cmd_list(registry: PluginRegistry, as_json: bool) -> Result[int, CliFailure]:
    """Print every plugin as a table, or as JSON with --json."""
    rows = [_row(r) for r in registry.records()]
    if as_json:
        _out(json.dumps(rows, indent=2))
        return Ok(Exit.OK)
    if not rows:
        _out("No plugins found.")
        return Ok(Exit.OK)
    table = [
        ("ID", "VERSION", "SOURCE", "STATE"),
        *(
            (str(r["id"]), str(r["version"] or "-"), str(r["source"]), str(r["state"]))
            for r in rows
        ),
    ]
    widths = [max(len(line[i]) for line in table) for i in range(4)]
    for line in table:
        _out("  ".join(c.ljust(w) for c, w in zip(line, widths, strict=True)).rstrip())
    return Ok(Exit.OK)


def _lookup(registry: PluginRegistry, plugin_id: str) -> Result[PluginRecord, CliFailure]:
    """Find a record or return the unknown-id failure listing known ids."""
    rec = registry.get(plugin_id)
    if rec is None:
        known = ", ".join(sorted(r.id for r in registry.records())) or "none"
        return Err(
            CliFailure(
                message=f"No plugin with id {plugin_id!r}. Known plugins: {known}.",
                code=Exit.UNKNOWN_PLUGIN,
            )
        )
    return Ok(rec)


def cmd_info(registry: PluginRegistry, plugin_id: str) -> Result[int, CliFailure]:
    """Print manifest, source, state and errors of one plugin."""
    found = _lookup(registry, plugin_id)
    if isinstance(found, Err):
        return Err(found.error)
    rec = found.value
    _out(f"id:       {rec.id}")
    _out(f"version:  {rec.manifest.version if rec.manifest else '-'}")
    _out(f"source:   {rec.source}")
    _out(f"state:    {rec.state.value}")
    if rec.manifest:
        _out(f"api:      {rec.manifest.api_version}")
        _out(f"labs:     {', '.join(rec.manifest.contributions.labs) or '-'}")
        _out(f"requires: {', '.join(r.id for r in rec.manifest.requires) or '-'}")
    if rec.errors:
        _out("errors:")
        for issue in rec.errors:
            _out(f"  - {issue.kind.name}: {issue.note}" if issue.note else f"  - {issue.kind.name}")
    return Ok(Exit.OK)


def cmd_set(
    registry: PluginRegistry, settings: PluginSettings, plugin_id: str, enabled: bool
) -> Result[int, CliFailure]:
    """Persist enable/disable for a known plugin and say when it takes effect."""
    found = _lookup(registry, plugin_id)
    if isinstance(found, Err):
        return Err(found.error)
    saved = set_enabled(settings.config_dir, plugin_id, enabled)
    if isinstance(saved, Err):
        return Err(_state_failure(saved))
    _out(f"Plugin {plugin_id} {'enabled' if enabled else 'disabled'}. {RESTART_NOTE}")
    return Ok(Exit.OK)


def build_parser() -> argparse.ArgumentParser:
    """Build the `sadi plugins` argument parser."""
    parser = argparse.ArgumentParser(prog="sadi plugins", description="Manage SADI plugins.")
    parser.add_argument("--config-dir", type=Path, help="override the user config directory")
    sub = parser.add_subparsers(dest="command", required=True)
    p_list = sub.add_parser("list", help="list discovered plugins")
    p_list.add_argument("--json", action="store_true", help="machine-readable output")
    sub.add_parser("info", help="show one plugin in detail").add_argument("id")
    sub.add_parser("enable", help="enable a plugin (next start)").add_argument("id")
    sub.add_parser("disable", help="disable a plugin (next start)").add_argument("id")
    return parser


def main(argv: Sequence[str] | None = None, sources: SourceFactory | None = None) -> int:
    """CLI entry point; returns the process exit code. `sources` builds the sources (tests)."""
    args = build_parser().parse_args(argv)
    settings = PluginSettings(config_dir=args.config_dir) if args.config_dir else PluginSettings()
    # INFO logs go to stdout and would corrupt table/--json output; keep warnings and errors.
    sadi_logger = logging.getLogger("sadi")
    previous = sadi_logger.level
    sadi_logger.setLevel(logging.WARNING)
    try:
        return _dispatch(args, settings, sources)
    finally:
        sadi_logger.setLevel(previous)


def _dispatch(
    args: argparse.Namespace, settings: PluginSettings, sources: SourceFactory | None
) -> int:
    """Discover plugins, run the chosen subcommand and render its failure, if any."""
    registry = _discover(settings, sources)
    if args.command == "list":
        result = cmd_list(registry, args.json)
    elif args.command == "info":
        result = cmd_info(registry, args.id)
    else:
        result = cmd_set(registry, settings, args.id, args.command == "enable")
    if isinstance(result, Err):
        _log.error("plugins %s failed: %s", args.command, result.error.message)
        _err(result.error.message)
        return result.error.code
    return result.value


if __name__ == "__main__":
    sys.exit(main())
