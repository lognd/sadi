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


class PluginImportError(ErrorSet):
    """Failure modes of importing a plugin and building its contributions."""

    ImportFailed = (
        "Plugin code raised while importing or registering; see the note and fix or disable it"
    )
    BadContribution = (
        "Plugin contribution is missing or has the wrong type; fix the entrypoint named in the note"
    )


class PluginRequiresError(ErrorSet):
    """Failure modes of resolving the plugins a plugin depends on."""

    Missing = "A required plugin is not installed or enabled; install or enable the one in the note"
    VersionMismatch = (
        "A required plugin is present at an unsupported version; update it as the note says"
    )


class PluginDuplicateIdError(ErrorSet):
    """Failure mode of two plugins claiming the same id."""

    Duplicate = "Another plugin already uses this id; remove or rename one of them"


class PluginSourceError(ErrorSet):
    """Failure modes of a plugin source while listing candidates."""

    Unavailable = "Source could not be listed; check the source configuration named in the note"
    BadCandidate = "Source entry could not be turned into a plugin; fix the entry named in the note"
