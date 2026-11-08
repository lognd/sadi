"""Plugin settings: extra plugin search paths and the user config dir for enable/disable state."""

# frob:ticket 01M6WFZ1R6ATYWRVW3315G6CCX

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from sadi.logging_setup import get_logger

_log = get_logger(__name__)

PLUGIN_PATH_ENV = "SADI_PLUGIN_PATH"
"""Environment variable holding an os.pathsep list of local plugin directories."""


def default_config_dir() -> Path:
    """Return the per-user SADI config dir (XDG_CONFIG_HOME/sadi or ~/.config/sadi)."""
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    return root / "sadi"


class PluginSettings(BaseModel):
    """User-level plugin configuration; enable/disable state lives under config_dir."""

    model_config = ConfigDict(frozen=True)

    plugin_paths: tuple[Path, ...] = ()
    config_dir: Path = Field(default_factory=default_config_dir)

    def effective_paths(self, env: dict[str, str] | None = None) -> tuple[Path, ...]:
        """Return SADI_PLUGIN_PATH entries when set (they win), else the settings plugin_paths."""
        raw = (os.environ if env is None else env).get(PLUGIN_PATH_ENV, "")
        entries = tuple(Path(p) for p in raw.split(os.pathsep) if p)
        if entries:
            _log.info("plugin paths from %s: %d", PLUGIN_PATH_ENV, len(entries))
            return entries
        return self.plugin_paths
