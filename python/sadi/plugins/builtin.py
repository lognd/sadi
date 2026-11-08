"""First-party plugin list: manifests shipped inside SADI, fed to BuiltinSource."""

# frob:ticket 01M6WFZ1N70HDJJRZWRHWP4E7Y

from __future__ import annotations

from importlib import resources

from typani import Ok

from sadi.logging_setup import get_logger
from sadi.plugins.manifest import PluginManifest, load_manifest_toml
from sadi.plugins.sources import BuiltinSource

_log = get_logger(__name__)

#: Packages under sadi that ship a sadi_plugin.toml and load as built-in plugins.
BUILTIN_PACKAGES: tuple[str, ...] = ("sadi.labs.lctt",)
MANIFEST_NAME = "sadi_plugin.toml"


def builtin_manifests() -> list[PluginManifest]:
    """Load the manifest of every built-in package; unreadable ones are logged and skipped."""
    out: list[PluginManifest] = []
    for pkg in BUILTIN_PACKAGES:
        path = resources.files(pkg).joinpath(MANIFEST_NAME)
        with resources.as_file(path) as real:
            loaded = load_manifest_toml(real)
        if isinstance(loaded, Ok):
            out.append(loaded.value)
        else:
            _log.error("built-in plugin %s manifest invalid: %s", pkg, loaded.unwrap_err())
    return out


def builtin_source() -> BuiltinSource:
    """Return the BuiltinSource listing all first-party plugins."""
    return BuiltinSource(builtin_manifests())
