"""Plugin doctor checks: pure findings over registry data, each with numbered fix steps."""

# frob:ticket 01M6WFZF4QDHYXTXX797A3KGX0

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from sadi.logging_setup import get_logger
from sadi.plugins.errors import (
    PluginApiVersionError,
    PluginDuplicateIdError,
    PluginImportError,
    PluginManifestError,
    PluginRequiresError,
    PluginSourceError,
)
from sadi.plugins.manifest import PLUGIN_API_VERSION
from sadi.plugins.registry import PluginRecord, PluginRegistry, PluginState
from sadi.plugins.sources import PluginIssue
from sadi.store.manifest import SessionPluginRef  # frob:ticket 01M6WHAKY5X32CK3JXWC13VH4Y

_log = get_logger(__name__)

_MAX_NOTE = 400


class Severity(StrEnum):
    """How bad a finding is: errors block a plugin, warnings degrade, info is advisory."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class DoctorFinding(BaseModel):
    """One plugin problem with a stable code and ordered, numbered fix steps."""

    model_config = ConfigDict(frozen=True)

    plugin_id: str
    severity: Severity
    code: str
    message: str
    fixes: tuple[str, ...]


def _numbered(steps: Sequence[str]) -> tuple[str, ...]:
    """Prefix each step with its 1-based number."""
    return tuple(f"{i}. {s}" for i, s in enumerate(steps, 1))


def _short(note: str) -> str:
    """Trim a note to a readable single-line summary."""
    flat = " ".join(note.split())
    return flat if len(flat) <= _MAX_NOTE else flat[: _MAX_NOTE - 3] + "..."


def _finding(
    pid: str, sev: Severity, code: str, message: str, steps: Sequence[str]
) -> DoctorFinding:
    """Build a finding, numbering its steps."""
    return DoctorFinding(
        plugin_id=pid, severity=sev, code=code, message=message, fixes=_numbered(steps)
    )


def _info_step(pid: str) -> str:
    """Step pointing at the detailed plugin report."""
    return f"Run `sadi plugins info {pid}` to see the full error detail."


def _issue_finding(rec: PluginRecord, issue: PluginIssue) -> DoctorFinding:
    """Map one record issue to a finding with concrete fix steps."""
    pid, note, kind = rec.id, _short(issue.note), issue.kind
    where = f"{rec.source}"
    if kind in (PluginImportError.ImportFailed, PluginImportError.BadContribution):
        bad = kind == PluginImportError.BadContribution
        return _finding(
            pid,
            Severity.ERROR,
            "plugin.import_failed" if not bad else "plugin.bad_contribution",
            f"Plugin {pid} ({where}) could not be loaded: {note}",
            [
                _info_step(pid),
                "Read the last line of the traceback summary above; it names the failing "
                "module and the exception.",
                "If it is ModuleNotFoundError, install the missing package into the SADI "
                "environment (`uv pip install <package>`)."
                if not bad
                else "Check each `contributions.labs` entry in the manifest is "
                "`module:attribute` and yields a LabModule with a valid lab id.",
                "Fix the plugin code, then re-run `sadi doctor` to confirm.",
                f"If you cannot fix it now, run `sadi plugins disable {pid}` so SADI starts "
                "without it.",
            ],
        )
    if kind == PluginApiVersionError.Incompatible:
        return _finding(
            pid,
            Severity.ERROR,
            "plugin.api_incompatible",
            f"Plugin {pid} does not support plugin API {PLUGIN_API_VERSION}: {note}",
            [
                f"This SADI provides plugin API {PLUGIN_API_VERSION}; the plugin's "
                "`api_version` range in its manifest excludes it.",
                f"Upgrade the plugin to a release whose api_version includes "
                f"{PLUGIN_API_VERSION} (`uv pip install -U <plugin-package>`).",
                "Or pin SADI to a release matching the plugin's api_version range "
                "(`uv pip install 'sadi==<version>'`).",
                "If you maintain the plugin, widen `api_version` in its manifest after "
                "testing, then re-run `sadi doctor`.",
            ],
        )
    if kind in (PluginRequiresError.Missing, PluginRequiresError.VersionMismatch):
        missing = kind == PluginRequiresError.Missing
        return _finding(
            pid,
            Severity.ERROR,
            "plugin.requires_missing" if missing else "plugin.requires_version",
            f"Plugin {pid} has an unmet dependency on another plugin: {note}",
            [
                "Open the plugin's manifest and read its `[[requires]]` entries; the note "
                "above names the unmet one.",
                "Install the required plugin (`uv pip install <plugin-package>`) or add its "
                "directory to SADI_PLUGIN_PATH."
                if missing
                else "Update the required plugin to a version inside the required range "
                "(`uv pip install -U <plugin-package>`).",
                "Run `sadi plugins list` and make sure the required plugin is enabled; "
                "enable it with `sadi plugins enable <required-id>`.",
                f"Re-run `sadi doctor`; {pid} should then load.",
            ],
        )
    if kind == PluginDuplicateIdError.Duplicate:
        return _finding(
            pid,
            Severity.ERROR,
            "plugin.duplicate_id",
            f"Plugin id {pid!r} is claimed twice: {note}",
            [
                "Run `sadi plugins list` to see every source that provides this id.",
                "Remove or uninstall the copy you do not want (`uv pip uninstall <package>` "
                "or delete its local plugin directory).",
                "Or, if both are wanted, change `id` in one manifest to a unique slug.",
                "Re-run `sadi doctor` to confirm only one remains.",
            ],
        )
    if isinstance(kind, PluginManifestError) or kind in tuple(PluginManifestError):
        return _manifest_finding(rec, issue)
    if kind in tuple(PluginSourceError):
        return _finding(
            pid,
            Severity.ERROR,
            "plugin.bad_candidate",
            f"Plugin entry {pid} ({where}) could not be turned into a plugin: {note}",
            [
                _info_step(pid),
                "Check that the entry point (or builtin entry) loads to a manifest or a "
                "zero-argument function returning one.",
                "Reinstall the package (`uv pip install --force-reinstall <package>`) in case "
                "the install is stale.",
                "If it stays broken, uninstall it (`uv pip uninstall <package>`).",
            ],
        )
    _log.warning("doctor: unmapped issue kind %r for %s", kind, pid)
    return _finding(
        pid,
        Severity.ERROR,
        "plugin.unknown_error",
        f"Plugin {pid} reported an unrecognized problem: {note}",
        [
            _info_step(pid),
            "Re-run `sadi doctor` with SADI_LOG_LEVEL=DEBUG and read the log.",
            f"Disable the plugin with `sadi plugins disable {pid}` until it is fixed.",
        ],
    )


def _manifest_finding(rec: PluginRecord, issue: PluginIssue) -> DoctorFinding:
    """Findings for manifest read/parse/validation problems, including bad local dirs."""
    pid, note, kind = rec.id, _short(issue.note), issue.kind
    local = rec.source == "local-dir"
    if kind == PluginManifestError.Unreadable:
        steps = (
            [
                "Open the plugin directory named in the note and check it contains "
                "`sadi_plugin.toml` (see `docs/plugins.md` for the format).",
                "If the file exists, check permissions (`ls -l`) so your user can read "
                "both the directory and the file.",
                "If the directory is not a plugin, remove it from `plugins/` / "
                "`private/*/plugin` or from SADI_PLUGIN_PATH.",
                "Re-run `sadi doctor` to confirm.",
            ]
            if local
            else [
                "Check the file path in the note exists and is readable by your user.",
                "Reinstall the package that provides it.",
                "Re-run `sadi doctor` to confirm.",
            ]
        )
        return _finding(
            pid,
            Severity.ERROR,
            "plugin.local_dir_unreadable" if local else "plugin.manifest_unreadable",
            f"Plugin {pid} manifest could not be read: {note}",
            steps,
        )
    syntax = kind == PluginManifestError.BadToml
    field = (
        "Fix the TOML syntax at the line named in the note (check quotes, brackets, `=`)."
        if syntax
        else "Edit the manifest so the field named in the note is present and valid "
        "(id: lowercase slug; version: PEP 440; api_version: specifier range)."
    )
    return _finding(
        pid,
        Severity.ERROR,
        "plugin.bad_toml" if syntax else "plugin.bad_manifest",
        f"Plugin {pid} has an invalid manifest: {note}",
        [
            f"Open the manifest of {pid} ({rec.source}); the note above says what is wrong.",
            field,
            "Validate by running `sadi plugins info <id>` or `sadi doctor` again.",
        ],
    )


def _record_findings(rec: PluginRecord) -> list[DoctorFinding]:
    """Findings for one record; always at least one when the record is not healthy."""
    pid = rec.id
    if rec.state is PluginState.ENABLED and not rec.errors:
        return []
    out = [_issue_finding(rec, i) for i in rec.errors]
    if rec.state is PluginState.DISABLED:
        out.append(
            _finding(
                pid,
                Severity.WARNING,
                "plugin.disabled",
                f"Plugin {pid} is disabled, so its contributions are not available.",
                [
                    f"Run `sadi plugins enable {pid}` to turn it back on.",
                    "Restart SADI (or re-run `sadi doctor`) so the change takes effect.",
                    "If it should stay off, no action is needed; this is only a reminder.",
                ],
            )
        )
    if not out:
        out.append(
            _finding(
                pid,
                Severity.ERROR,
                "plugin.unhealthy",
                f"Plugin {pid} is in state {rec.state.value} with no recorded cause.",
                [
                    _info_step(pid),
                    "Re-run `sadi doctor` with SADI_LOG_LEVEL=DEBUG and read the log.",
                    f"Disable it with `sadi plugins disable {pid}` until resolved.",
                ],
            )
        )
    return out


def _source_findings(issues: Sequence[PluginIssue]) -> list[DoctorFinding]:
    """Findings for whole-source failures."""
    return [
        _finding(
            "(source)",
            Severity.ERROR,
            "plugin.source_unavailable",
            f"A plugin source could not be listed: {_short(i.note)}",
            [
                "The note above starts with the source name (builtin, entry-points, local-dir).",
                "For local-dir, check SADI_PLUGIN_PATH and the plugin_paths setting point "
                "at existing, readable directories.",
                "For entry-points, reinstall SADI's environment (`uv sync`) to rebuild "
                "package metadata.",
                "Re-run `sadi doctor` to confirm.",
            ],
        )
        for i in issues
    ]


def _session_findings(
    registry: PluginRegistry, refs: Sequence[SessionPluginRef]
) -> list[DoctorFinding]:
    """Findings for plugins a session used that are missing, disabled or changed version."""
    out: list[DoctorFinding] = []
    for ref in refs:
        rec = registry.get(ref.id)
        usable = rec is not None and rec.state is PluginState.ENABLED
        if rec is None or rec.state is not PluginState.ENABLED:
            why = "is not installed" if rec is None else f"is {rec.state.value}"
            out.append(
                _finding(
                    ref.id,
                    Severity.WARNING,
                    "session.plugin_missing",
                    f"This session used plugin {ref.id} {ref.version}, which {why}.",
                    [
                        f"Install the plugin (`uv pip install <package>`) or place it in "
                        f"`plugins/`, version {ref.version} if you need identical results."
                        if rec is None
                        else f"Run `sadi plugins enable {ref.id}` and fix any errors "
                        "`sadi doctor` reports for it.",
                        "Reopen the session; stored data stays readable without the plugin.",
                        "If the plugin is retired, no action is needed; the session is "
                        "read-only for its contributions.",
                    ],
                )
            )
        elif usable and rec.manifest is not None and rec.manifest.version != ref.version:
            out.append(
                _finding(
                    ref.id,
                    Severity.INFO,
                    "session.plugin_version_changed",
                    f"Session used {ref.id} {ref.version}; {rec.manifest.version} is installed.",
                    [
                        f"If you need to reproduce the session exactly, install version "
                        f"{ref.version} (`uv pip install '<package>=={ref.version}'`).",
                        "Otherwise no action is needed; results may differ slightly.",
                    ],
                )
            )
    return out


def check_plugins(
    registry: PluginRegistry, session_refs: Sequence[SessionPluginRef] = ()
) -> list[DoctorFinding]:
    """Return findings for every unhealthy plugin state; pure, never raises."""
    findings: list[DoctorFinding] = []
    for rec in registry.records():
        findings.extend(_record_findings(rec))
    findings.extend(_source_findings(registry.source_errors()))
    findings.extend(_session_findings(registry, session_refs))
    _log.info("plugin doctor: %d findings", len(findings))
    return findings


__all__ = ["DoctorFinding", "SessionPluginRef", "Severity", "check_plugins"]
