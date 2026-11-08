"""SADI plugin system: manifest model and plugin-API compatibility."""

# frob:ticket 01M6WFYFTBG9T5MNPJJC0E4R63

from sadi.plugins.errors import PluginApiVersionError, PluginManifestError
from sadi.plugins.manifest import (
    PLUGIN_API_VERSION,
    PluginContributions,
    PluginManifest,
    PluginRequirement,
    check_api_compat,
    load_manifest_toml,
    parse_manifest,
)

__all__ = [
    "PLUGIN_API_VERSION",
    "PluginApiVersionError",
    "PluginContributions",
    "PluginManifest",
    "PluginManifestError",
    "PluginRequirement",
    "check_api_compat",
    "load_manifest_toml",
    "parse_manifest",
]
