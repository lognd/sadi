"""Local-dir plugin source: loads plugins by path with no install, under a private namespace."""

# frob:ticket 01M6WFZ1R6ATYWRVW3315G6CCX

from __future__ import annotations

import importlib.util
import sys
import types
from collections.abc import Sequence
from importlib.machinery import ModuleSpec
from pathlib import Path

from typani import Err, Ok, Result

from sadi.logging_setup import get_logger
from sadi.plugins.errors import PluginImportError, PluginManifestError, PluginSourceError
from sadi.plugins.manifest import PluginContributions, PluginManifest, load_manifest_toml
from sadi.plugins.settings import PluginSettings
from sadi.plugins.sources import PluginCandidate, PluginIssue

_log = get_logger(__name__)

MANIFEST_NAME = "sadi_plugin.toml"
"""File that marks a directory as a plugin."""

NAMESPACE = "sadi_local_plugins"
"""Parent module name every local plugin is loaded under, so it can never shadow core."""

_REPO_ROOT = Path(__file__).resolve().parents[3]


def default_dirs(root: Path | None = None) -> list[Path]:
    """Return the existing default plugin dirs: <root>/plugins and <root>/private/*/plugin."""
    base = root or _REPO_ROOT
    cands = [base / "plugins", *sorted((base / "private").glob("*/plugin"))]
    return [p for p in cands if p.is_dir()]


def _plugin_dirs(entry: Path) -> list[Path]:
    """Expand a search entry: itself when it holds a manifest, else its child plugin dirs."""
    if (entry / MANIFEST_NAME).is_file():
        return [entry]
    try:
        return sorted(
            p for p in entry.iterdir() if p.is_dir() and not p.name.startswith((".", "_"))
        )
    except OSError as exc:
        _log.warning("cannot list plugin dir %s: %s", entry, exc)
        return []


def _module_name(plugin_id: str) -> str:
    """Namespaced module name for a plugin id."""
    return f"{NAMESPACE}.{plugin_id.replace('-', '_')}"


def _ensure_namespace() -> None:
    """Make sure the empty parent package exists in sys.modules."""
    if NAMESPACE not in sys.modules:
        pkg = types.ModuleType(NAMESPACE)
        pkg.__path__ = []
        sys.modules[NAMESPACE] = pkg


def _load_package(manifest: PluginManifest, directory: Path) -> PluginIssue | None:
    """Import the plugin dir as package sadi_local_plugins.<id>; return an issue on failure."""
    name = _module_name(manifest.id)
    init = directory / "__init__.py"
    if init.is_file():
        spec = importlib.util.spec_from_file_location(
            name, init, submodule_search_locations=[str(directory)]
        )
    else:
        spec = ModuleSpec(name, None, is_package=True)
        spec.submodule_search_locations = [str(directory)]
    if spec is None:
        return PluginIssue(kind=PluginImportError.ImportFailed, note=f"{directory}: no import spec")
    _ensure_namespace()
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        if init.is_file() and spec.loader is not None:
            spec.loader.exec_module(module)
    except Exception as exc:  # noqa: BLE001 - plugin code is untrusted; report as value
        sys.modules.pop(name, None)
        _log.exception("local plugin %s failed to import", manifest.id)
        return PluginIssue(kind=PluginImportError.ImportFailed, note=f"{directory}: {exc!r}")
    return None


def _rebase(manifest: PluginManifest) -> PluginManifest:
    """Prefix each contribution ref with the plugin's namespaced package name."""
    prefix = _module_name(manifest.id)
    c = manifest.contributions
    moved = PluginContributions(
        labs=tuple(f"{prefix}.{r}" for r in c.labs),
        exports=tuple(f"{prefix}.{r}" for r in c.exports),
        jobs=tuple(f"{prefix}.{r}" for r in c.jobs),
        panels=tuple(f"{prefix}.{r}" for r in c.panels),
    )
    return manifest.model_copy(update={"contributions": moved})


class LocalDirSource:
    """Plugins found in local dirs (env, settings, or default plugins/ and private/*/plugin)."""

    name = "local-dir"

    # frob:ticket 01M6WHAW41PYAKM3VTPTTS9C1J
    def __init__(
        self,
        paths: Sequence[Path] | None = None,
        settings: PluginSettings | None = None,
        root: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        """Pick search paths: explicit `paths`, else env/settings, else defaults under `root`."""
        explicit = (
            tuple(paths)
            if paths is not None
            else (settings or PluginSettings()).effective_paths(env)
        )
        self._paths = list(explicit) if explicit else default_dirs(root)

    def discover(self) -> Result[list[PluginCandidate], PluginSourceError]:
        """Load every plugin dir found; missing dirs are skipped, bad ones become issue records."""
        out: list[PluginCandidate] = []
        for entry in self._paths:
            if not entry.is_dir():
                _log.info("local plugin dir absent, skipping: %s", entry)
                continue
            for directory in _plugin_dirs(entry):
                out.append(self._load_dir(directory))
        _log.info("local-dir source: %d candidates", len(out))
        return Ok(out)

    def _load_dir(self, directory: Path) -> PluginCandidate:
        """Turn one plugin directory into a candidate without raising."""
        manifest_path = directory / MANIFEST_NAME
        if not manifest_path.is_file():
            note = f"{directory}: no {MANIFEST_NAME}"
            return PluginCandidate(
                name=directory.name,
                source=self.name,
                issues=(PluginIssue(kind=PluginManifestError.Unreadable, note=note),),
            )
        parsed = load_manifest_toml(manifest_path)
        if isinstance(parsed, Err):
            return PluginCandidate(
                name=directory.name,
                source=self.name,
                issues=(PluginIssue(kind=parsed.error, note="; ".join(parsed.notes)),),
            )
        manifest = parsed.value
        issue = _load_package(manifest, directory)
        if issue is not None:
            return PluginCandidate(name=manifest.id, source=self.name, issues=(issue,))
        _log.info("local plugin %s loaded from %s", manifest.id, directory)
        return PluginCandidate(name=manifest.id, source=self.name, manifest=_rebase(manifest))
