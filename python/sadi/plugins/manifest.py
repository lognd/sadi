"""Plugin manifest model, TOML loading and plugin-API compatibility check."""

# frob:ticket 01M6WFYFTBG9T5MNPJJC0E4R63

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Annotated

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, ValidationError
from typani import Err, Ok, Result

from sadi.logging_setup import get_logger
from sadi.plugins.errors import PluginApiVersionError, PluginManifestError

_log = get_logger(__name__)

PLUGIN_API_VERSION = "1.0"
"""Version of the plugin API this SADI build offers; plugins declare a range over it."""

_SLUG = re.compile(r"^[a-z][a-z0-9_-]*$")
_ENTRYPOINT = re.compile(r"^[A-Za-z_][\w.]*:[A-Za-z_][\w.]*$")


def _check_slug(value: str) -> str:
    """Validate a plugin id slug (lowercase letters, digits, '-' and '_')."""
    if not _SLUG.fullmatch(value):
        raise ValueError(f"{value!r} is not a slug like 'my-plugin'")
    return value


def _check_version(value: str) -> str:
    """Validate a PEP 440 version string."""
    try:
        Version(value)
    except InvalidVersion as exc:
        raise ValueError(f"{value!r} is not a PEP 440 version") from exc
    return value


def _check_specifier(value: str) -> str:
    """Validate a PEP 440 specifier range such as '>=1,<2'."""
    try:
        SpecifierSet(value)
    except InvalidSpecifier as exc:
        raise ValueError(f"{value!r} is not a PEP 440 specifier range") from exc
    return value


def _check_entrypoint(value: str) -> str:
    """Validate an entrypoint reference of the form 'package.module:attr'."""
    if not _ENTRYPOINT.fullmatch(value):
        raise ValueError(f"{value!r} is not an entrypoint like 'pkg.mod:attr'")
    return value


PluginId = Annotated[str, AfterValidator(_check_slug)]
PluginVersion = Annotated[str, AfterValidator(_check_version)]
VersionRange = Annotated[str, AfterValidator(_check_specifier)]
EntrypointRef = Annotated[str, AfterValidator(_check_entrypoint)]


class PluginRequirement(BaseModel):
    """A dependency on another plugin: its id and an acceptable version range."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: PluginId
    version: VersionRange = ""


class PluginContributions(BaseModel):
    """What a plugin adds to SADI; only labs are live, the rest are reserved and empty."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    labs: tuple[EntrypointRef, ...] = ()
    exports: tuple[EntrypointRef, ...] = ()
    jobs: tuple[EntrypointRef, ...] = ()
    panels: tuple[EntrypointRef, ...] = ()


class PluginManifest(BaseModel):
    """Validated, immutable description of one plugin."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: PluginId
    version: PluginVersion
    api_version: VersionRange
    contributions: PluginContributions = Field(default_factory=PluginContributions)
    requires: tuple[PluginRequirement, ...] = ()


def _describe(exc: ValidationError) -> tuple[PluginManifestError, str]:
    """Map a pydantic failure to MissingField or InvalidField plus a field-level note."""
    errors = exc.errors()
    missing = [e for e in errors if e["type"] == "missing"]
    chosen = missing or errors
    kind = PluginManifestError.MissingField if missing else PluginManifestError.InvalidField
    parts = [f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in chosen]
    return kind, "; ".join(parts)


def parse_manifest(data: dict[str, object]) -> Result[PluginManifest, PluginManifestError]:
    """Validate a manifest mapping; Err names the offending fields instead of raising."""
    try:
        manifest = PluginManifest.model_validate(data)
    except ValidationError as exc:
        kind, text = _describe(exc)
        _log.warning("manifest invalid (%s): %s", kind.name, text)
        return Err[PluginManifest, PluginManifestError](kind).note(text)
    _log.debug("manifest ok: %s %s", manifest.id, manifest.version)
    return Ok(manifest)


def load_manifest_toml(path: Path) -> Result[PluginManifest, PluginManifestError]:
    """Read and validate a plugin manifest TOML file; never raises for bad input."""
    try:
        raw = path.read_bytes()
    except OSError as exc:
        _log.warning("manifest unreadable %s: %s", path, exc)
        return Err[PluginManifest, PluginManifestError](PluginManifestError.Unreadable).note(
            f"{path}: {exc}"
        )
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        _log.warning("manifest not toml %s: %s", path, exc)
        return Err[PluginManifest, PluginManifestError](PluginManifestError.BadToml).note(
            f"{path}: {exc}"
        )
    _log.info("loading manifest %s", path)
    return parse_manifest(data).note(f"while loading {path}")


def check_api_compat(manifest: PluginManifest) -> Result[None, PluginApiVersionError]:
    """Return Ok when the host PLUGIN_API_VERSION satisfies the manifest api_version range."""
    if SpecifierSet(manifest.api_version).contains(Version(PLUGIN_API_VERSION), prereleases=True):
        _log.debug("plugin %s api ok (%s)", manifest.id, manifest.api_version)
        return Ok(None)
    msg = (
        f"plugin {manifest.id} {manifest.version} requires plugin api "
        f"'{manifest.api_version}' but this SADI provides {PLUGIN_API_VERSION}"
    )
    _log.warning(msg)
    return Err[None, PluginApiVersionError](PluginApiVersionError.Incompatible).note(msg)
