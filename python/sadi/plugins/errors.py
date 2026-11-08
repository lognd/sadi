"""Typed errors for the plugin system; each member's description says what to do next."""

# frob:ticket 01M6WFYFTBG9T5MNPJJC0E4R63

from __future__ import annotations

from typani import ErrorSet


class PluginManifestError(ErrorSet):
    """Failure modes of reading and validating a plugin manifest."""

    Unreadable = "Manifest file could not be read; check the path and file permissions"
    BadToml = "Manifest is not valid TOML; fix the syntax at the line named in the note"
    MissingField = "Manifest lacks a required field; add the field named in the note"
    InvalidField = "Manifest field has a bad value; correct the field named in the note"


class PluginApiVersionError(ErrorSet):
    """Failure modes of checking a plugin against the host plugin API version."""

    Incompatible = (
        "Plugin does not support this SADI plugin API; update the plugin or SADI to match"
    )
