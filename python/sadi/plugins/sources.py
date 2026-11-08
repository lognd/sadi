"""Plugin sources: where candidate plugins come from (built-in list, entry points)."""

# frob:ticket 01M6WFYN8C6YH5D79CPEKSP69P

from __future__ import annotations

from collections.abc import Callable, Sequence
from importlib.metadata import entry_points
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict
from typani import Err, ErrorSet, Ok, Result

from sadi.logging_setup import get_logger
from sadi.plugins.errors import PluginManifestError, PluginSourceError
from sadi.plugins.manifest import PluginManifest, parse_manifest

_log = get_logger(__name__)

PLUGIN_ENTRY_POINT_GROUP = "sadi.plugins"
"""Entry-point group installed packages register plugins under."""


class PluginIssue(BaseModel):
    """One typed error plus a human note; the unit of per-plugin failure reporting."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    kind: ErrorSet
    note: str = ""


class PluginCandidate(BaseModel):
    """A plugin a source found: a manifest, or the issues that kept one from forming."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    name: str
    source: str
    manifest: PluginManifest | None = None
    issues: tuple[PluginIssue, ...] = ()


@runtime_checkable
class PluginSource(Protocol):
    """Something that lists plugin candidates; must not raise for bad entries."""

    name: str

    def discover(self) -> Result[list[PluginCandidate], PluginSourceError]:
        """List candidates, deterministic order; per-entry problems live on the candidate."""
        ...


class BuiltinSource:
    """Explicit first-party plugin list shipped inside SADI."""

    name = "builtin"

    def __init__(self, manifests: Sequence[PluginManifest | dict[str, object]] = ()) -> None:
        """Hold the first-party manifests (objects or raw mappings) in given order."""
        self._entries = tuple(manifests)

    def discover(self) -> Result[list[PluginCandidate], PluginSourceError]:
        """Return one candidate per entry; invalid mappings become issue-bearing candidates."""
        out: list[PluginCandidate] = []
        for i, entry in enumerate(self._entries):
            out.append(_candidate_from(f"builtin[{i}]", self.name, entry))
        _log.info("builtin source: %d candidates", len(out))
        return Ok(out)


def _candidate_from(name: str, source: str, obj: object) -> PluginCandidate:
    """Turn a manifest or mapping into a candidate, capturing validation failures."""
    if isinstance(obj, PluginManifest):
        return PluginCandidate(name=obj.id, source=source, manifest=obj)
    if isinstance(obj, dict):
        parsed = parse_manifest(obj)
        if isinstance(parsed, Ok):
            return PluginCandidate(name=parsed.value.id, source=source, manifest=parsed.value)
        err = parsed.error
        note = "; ".join((name, *parsed.notes))
        return PluginCandidate(
            name=str(obj.get("id", name)),
            source=source,
            issues=(PluginIssue(kind=err, note=note),),
        )
    _log.warning("%s: unsupported manifest object %r", name, type(obj).__name__)
    return PluginCandidate(
        name=name,
        source=source,
        issues=(
            PluginIssue(
                kind=PluginManifestError.InvalidField,
                note=f"{name}: expected a manifest or mapping, got {type(obj).__name__}",
            ),
        ),
    )


class EntryPointSource:
    """Installed packages registered under the `sadi.plugins` entry-point group.

    Each entry point loads to a PluginManifest, a manifest mapping, or a zero-arg callable
    returning either.
    """

    name = "entry-points"

    def __init__(
        self, group: str = PLUGIN_ENTRY_POINT_GROUP, lister: Callable[..., object] | None = None
    ) -> None:
        """Choose the group to read; `lister` overrides entry_points for tests."""
        self._group = group
        self._lister = lister or entry_points

    def discover(self) -> Result[list[PluginCandidate], PluginSourceError]:
        """Load every entry point; a failing one yields a candidate with an issue."""
        try:
            eps = sorted(self._lister(group=self._group), key=lambda e: e.name)  # type: ignore[attr-defined]
        except (OSError, ValueError, TypeError) as exc:  # metadata backend is outside our control
            _log.exception("entry point listing failed for %s", self._group)
            return Err(PluginSourceError.Unavailable).note(f"{self._group}: {exc}")
        out: list[PluginCandidate] = []
        for ep in eps:
            out.append(self._load_one(ep))
        _log.info("entry-point source %s: %d candidates", self._group, len(out))
        return Ok(out)

    def _load_one(self, ep: object) -> PluginCandidate:
        """Load one entry point into a candidate without raising."""
        name = str(getattr(ep, "name", "?"))
        try:
            obj = ep.load()  # type: ignore[attr-defined]
            if callable(obj) and not isinstance(obj, (PluginManifest, dict)):
                obj = obj()
        except Exception as exc:  # noqa: BLE001 - third-party code; report as value
            _log.exception("entry point %s failed to load", name)
            return PluginCandidate(
                name=name,
                source=self.name,
                issues=(PluginIssue(kind=PluginSourceError.BadCandidate, note=f"{name}: {exc!r}"),),
            )
        return _candidate_from(name, self.name, obj)
