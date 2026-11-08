"""SADI plugin system: manifest, compatibility, sources and registry."""

# frob:ticket 01M6WFYFTBG9T5MNPJJC0E4R63
# frob:ticket 01M6WFYN8C6YH5D79CPEKSP69P

from sadi.plugins.errors import (
    PluginApiVersionError,
    PluginDuplicateIdError,
    PluginImportError,
    PluginManifestError,
    PluginRequiresError,
    PluginSourceError,
)
from sadi.plugins.manifest import (
    PLUGIN_API_VERSION,
    PluginContributions,
    PluginManifest,
    PluginRequirement,
    check_api_compat,
    load_manifest_toml,
    parse_manifest,
)
from sadi.plugins.registry import PluginRecord, PluginRegistry, PluginState
from sadi.plugins.sources import (
    BuiltinSource,
    EntryPointSource,
    PluginCandidate,
    PluginIssue,
    PluginSource,
)

__all__ = [
    "BuiltinSource",
    "EntryPointSource",
    "PluginCandidate",
    "PluginDuplicateIdError",
    "PluginImportError",
    "PluginIssue",
    "PluginRecord",
    "PluginRegistry",
    "PluginRequiresError",
    "PluginSource",
    "PluginSourceError",
    "PluginState",
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
