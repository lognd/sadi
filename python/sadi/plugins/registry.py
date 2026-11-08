"""PluginRegistry: discover, vet and load plugins from sources; failures become records."""

# frob:ticket 01M6WFYN8C6YH5D79CPEKSP69P

from __future__ import annotations

import importlib
from collections.abc import Collection, Sequence
from datetime import UTC, datetime
from enum import StrEnum

from packaging.specifiers import SpecifierSet
from packaging.version import Version
from pydantic import BaseModel, ConfigDict
from typani import Err

from sadi.core.lab import LabModule
from sadi.core.registry import validate_lab
from sadi.logging_setup import get_logger
from sadi.plugins.errors import (
    PluginDuplicateIdError,
    PluginImportError,
    PluginRequiresError,
    PluginSourceError,
)
from sadi.plugins.manifest import PluginManifest, check_api_compat
from sadi.plugins.sources import PluginCandidate, PluginIssue, PluginSource

_log = get_logger(__name__)


class PluginState(StrEnum):
    """Lifecycle state of one discovered plugin."""

    ENABLED = "enabled"
    DISABLED = "disabled"
    FAILED = "failed"
    INCOMPATIBLE = "incompatible"


class PluginRecord(BaseModel):
    """What discovery learned about one plugin: manifest, source, state and errors."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    name: str
    source: str
    state: PluginState
    manifest: PluginManifest | None = None
    errors: tuple[PluginIssue, ...] = ()
    labs: tuple[LabModule, ...] = ()
    loaded_at: datetime | None = None

    @property
    def id(self) -> str:
        """Plugin id from the manifest, or the candidate name when no manifest formed."""
        return self.manifest.id if self.manifest else self.name


def _fail(rec: PluginRecord, state: PluginState, *issues: PluginIssue) -> PluginRecord:
    """Return a copy of `rec` moved to `state` with `issues` appended and labs dropped."""
    _log.warning("plugin %s -> %s: %s", rec.id, state.value, [i.note for i in issues])
    return rec.model_copy(update={"state": state, "errors": rec.errors + issues, "labs": ()})


def _unmet(manifest: PluginManifest, live: dict[str, str]) -> list[PluginIssue]:
    """List unmet `requires` of `manifest` against live plugin id -> version."""
    out: list[PluginIssue] = []
    for req in manifest.requires:
        have = live.get(req.id)
        if have is None:
            out.append(
                PluginIssue(
                    kind=PluginRequiresError.Missing,
                    note=f"{manifest.id} requires plugin {req.id!r}",
                )
            )
        elif req.version and not SpecifierSet(req.version).contains(
            Version(have), prereleases=True
        ):
            out.append(
                PluginIssue(
                    kind=PluginRequiresError.VersionMismatch,
                    note=f"{manifest.id} requires {req.id} {req.version} but found {have}",
                )
            )
    return out


def _load_labs(manifest: PluginManifest) -> tuple[LabModule, ...]:
    """Import each lab factory ref and build the labs; raises on any problem (caller guards)."""
    labs: list[LabModule] = []
    for ref in manifest.contributions.labs:
        module_name, _, attr = ref.partition(":")
        obj = importlib.import_module(module_name)
        for part in attr.split("."):
            obj = getattr(obj, part)
        lab = obj() if callable(obj) else obj
        if not isinstance(lab, LabModule):
            raise TypeError(f"{ref} did not yield a LabModule")
        checked = validate_lab(lab)
        if isinstance(checked, Err):
            raise ValueError(
                f"{ref}: invalid lab ({checked.error.code.name}: {checked.error.detail})"
            )
        labs.append(lab)
    return tuple(labs)


def _import(rec: PluginRecord) -> PluginRecord:
    """Import a vetted plugin inside a guard; any exception becomes a failed record."""
    assert rec.manifest is not None
    try:
        labs = _load_labs(rec.manifest)
    except Exception as exc:  # noqa: BLE001 - plugin code is untrusted; isolate it
        _log.exception("plugin %s failed to import", rec.id)
        kind = (
            PluginImportError.BadContribution
            if isinstance(exc, (TypeError, ValueError))
            else PluginImportError.ImportFailed
        )
        return _fail(rec, PluginState.FAILED, PluginIssue(kind=kind, note=f"{exc!r}"))
    _log.info("plugin %s loaded (%d labs)", rec.id, len(labs))
    return rec.model_copy(update={"labs": labs, "loaded_at": datetime.now(UTC)})


class PluginRegistry:
    """Immutable-after-discovery set of PluginRecords in deterministic order."""

    def __init__(
        self,
        records: Sequence[PluginRecord] = (),
        source_errors: Sequence[PluginIssue] = (),
    ) -> None:
        """Hold the records and any whole-source failures."""
        self._records = tuple(records)
        self._source_errors = tuple(source_errors)

    @classmethod
    def discover(
        cls, sources: Sequence[PluginSource], disabled: Collection[str] = ()
    ) -> PluginRegistry:
        """Build a registry from sources; never raises, every failure is a record or issue."""
        records: list[PluginRecord] = []
        source_errors: list[PluginIssue] = []
        for source in sources:
            try:
                found = source.discover()
            except Exception as exc:  # noqa: BLE001 - a broken source must not abort discovery
                _log.exception("source %s raised", getattr(source, "name", source))
                source_errors.append(
                    PluginIssue(kind=PluginSourceError.Unavailable, note=f"{exc!r}")
                )
                continue
            if isinstance(found, Err):
                note = "; ".join((getattr(source, "name", "?"), *found.notes))
                source_errors.append(PluginIssue(kind=found.error, note=note))
                continue
            records.extend(cls._vet(c, disabled, records) for c in found.value)
        records = cls._resolve_requires(records)
        records = [_import(r) if cls._pending(r) else r for r in records]
        records = cls._resolve_requires(records, loaded_only=True)
        _log.info("plugins: %d records, %d source errors", len(records), len(source_errors))
        return cls(records, source_errors)

    @staticmethod
    def _pending(rec: PluginRecord) -> bool:
        """True when a record passed vetting and still needs importing."""
        return rec.state is PluginState.ENABLED and rec.loaded_at is None

    @staticmethod
    def _vet(
        cand: PluginCandidate, disabled: Collection[str], prior: Sequence[PluginRecord]
    ) -> PluginRecord:
        """Make a record from a candidate: manifest errors, duplicates, api, disabled."""
        rec = PluginRecord(
            name=cand.name,
            source=cand.source,
            state=PluginState.ENABLED,
            manifest=cand.manifest,
            errors=cand.issues,
        )
        if cand.manifest is None:
            return _fail(rec, PluginState.FAILED)
        mf = cand.manifest
        if any(p.manifest and p.manifest.id == mf.id for p in prior):
            return _fail(
                rec,
                PluginState.FAILED,
                PluginIssue(
                    kind=PluginDuplicateIdError.Duplicate,
                    note=f"id {mf.id!r} from {cand.source} already registered",
                ),
            )
        compat = check_api_compat(mf)
        if isinstance(compat, Err):
            return _fail(
                rec,
                PluginState.INCOMPATIBLE,
                PluginIssue(kind=compat.error, note="; ".join(compat.notes)),
            )
        if mf.id in disabled:
            _log.info("plugin %s disabled; not imported", mf.id)
            return rec.model_copy(update={"state": PluginState.DISABLED})
        return rec

    @staticmethod
    def _resolve_requires(
        records: list[PluginRecord], loaded_only: bool = False
    ) -> list[PluginRecord]:
        """Fail enabled plugins whose requires are unmet, repeating until stable."""
        current = list(records)
        while True:
            live = {
                r.id: r.manifest.version
                for r in current
                if r.manifest
                and r.state is PluginState.ENABLED
                and (r.loaded_at is not None or not loaded_only)
            }
            changed = False
            for i, r in enumerate(current):
                if r.state is not PluginState.ENABLED or r.manifest is None:
                    continue
                issues = _unmet(r.manifest, live)
                if issues:
                    current[i] = _fail(r, PluginState.FAILED, *issues)
                    changed = True
            if not changed:
                return current

    def records(self) -> list[PluginRecord]:
        """Return all records in deterministic discovery order."""
        return list(self._records)

    def source_errors(self) -> list[PluginIssue]:
        """Return failures of whole sources (as opposed to single plugins)."""
        return list(self._source_errors)

    def get(self, plugin_id: str) -> PluginRecord | None:
        """Return the first record with this id, or None."""
        return next((r for r in self._records if r.id == plugin_id), None)

    def labs(self) -> list[LabModule]:
        """Return labs of every enabled plugin, in record order."""
        return [lab for r in self._records if r.state is PluginState.ENABLED for lab in r.labs]
