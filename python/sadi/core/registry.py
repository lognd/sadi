"""Lab registry: a validated view over plugin labs plus legacy `sadi.labs` entry points."""

# frob:ticket 01M6W7R1G903HZ7V7JRCYC6ZT7
# frob:ticket 01M6WFYN8C6YH5D79CPEKSP69P

from __future__ import annotations

from importlib.metadata import entry_points
from typing import TYPE_CHECKING

from typani import Err, Ok, Result

from sadi.core.errors import InputCode, InputError
from sadi.core.lab import ENTRY_POINT_GROUP, LabId, LabModule
from sadi.logging_setup import get_logger

if TYPE_CHECKING:
    from sadi.plugins.registry import PluginRegistry

_log = get_logger(__name__)


def validate_lab(lab: LabModule) -> Result[LabModule, InputError]:
    """Check a lab is registrable: non-empty id, steps with unique ids, unique export ids."""
    if not lab.id:
        _log.warning("lab with empty id rejected")
        return Err(InputError(code=InputCode.MISSING, detail="lab id"))
    steps = lab.steps()
    if not steps:
        _log.warning("lab %s declares no steps", lab.id)
        return Err(InputError(code=InputCode.MISSING, detail=f"{lab.id}: steps"))
    step_ids = [s.id for s in steps]
    if len(set(step_ids)) != len(step_ids):
        _log.warning("lab %s has duplicate step ids", lab.id)
        return Err(InputError(code=InputCode.DUPLICATE, detail=f"{lab.id}: step id"))
    fmt_ids = [f.id for f in lab.export_formats]
    if len(set(fmt_ids)) != len(fmt_ids):
        _log.warning("lab %s has duplicate export format ids", lab.id)
        return Err(InputError(code=InputCode.DUPLICATE, detail=f"{lab.id}: export format id"))
    return Ok(lab)


class LabRegistry:
    """In-process registry of labs keyed by LabId; registration is validated and ordered."""

    def __init__(self) -> None:
        """Create an empty registry."""
        self._labs: dict[LabId, LabModule] = {}

    def register(self, lab: LabModule) -> Result[None, InputError]:
        """Add a validated lab; Err(DUPLICATE) if its id is taken, Err(MISSING) if malformed."""
        checked = validate_lab(lab)
        if isinstance(checked, Err):
            return Err(checked.error)
        if lab.id in self._labs:
            _log.warning("lab %s already registered", lab.id)
            return Err(InputError(code=InputCode.DUPLICATE, detail=lab.id))
        self._labs[lab.id] = lab
        _log.info("registered lab %s", lab.id)
        return Ok(None)

    def get(self, lab_id: LabId) -> Result[LabModule, InputError]:
        """Look a lab up by id; Err(UNKNOWN_ID) when absent."""
        lab = self._labs.get(lab_id)
        if lab is None:
            _log.warning("unknown lab %r", lab_id)
            return Err(InputError(code=InputCode.UNKNOWN_ID, detail=lab_id))
        return Ok(lab)

    def ids(self) -> list[LabId]:
        """Return registered lab ids in registration order."""
        return list(self._labs)

    def add_plugins(self, plugins: PluginRegistry) -> list[InputError]:
        """Register the labs of every enabled plugin (view over a PluginRegistry); return errors."""
        errors: list[InputError] = []
        for lab in plugins.labs():
            result = self.register(lab)
            if isinstance(result, Err):
                errors.append(result.error)
        _log.info("added plugin labs: %d labs, %d errors", len(self._labs), len(errors))
        return errors

    @classmethod
    def from_plugins(cls, plugins: PluginRegistry) -> LabRegistry:
        """Build a LabRegistry viewing the labs of a PluginRegistry."""
        reg = cls()
        reg.add_plugins(plugins)
        return reg

    def discover(self) -> list[InputError]:
        """Load every legacy `sadi.labs` entry point (a zero-arg factory returning a LabModule).

        The `sadi.labs` group is deprecated in favour of `sadi.plugins`; it is still read.

        Returns the errors of entries that failed to load or register; others still register.
        """
        errors: list[InputError] = []
        for ep in entry_points(group=ENTRY_POINT_GROUP):
            _log.warning(
                "entry point %s uses deprecated group %s; migrate to sadi.plugins",
                ep.name,
                ENTRY_POINT_GROUP,
            )
            try:
                lab = ep.load()()
            except Exception:  # noqa: BLE001 - third-party factory; report, keep going
                _log.exception("entry point %s failed to load", ep.name)
                errors.append(InputError(code=InputCode.MISSING, detail=f"entry point {ep.name}"))
                continue
            if not isinstance(lab, LabModule):
                _log.warning("entry point %s did not yield a LabModule", ep.name)
                errors.append(InputError(code=InputCode.MISSING, detail=f"entry point {ep.name}"))
                continue
            result = self.register(lab)
            if isinstance(result, Err):
                errors.append(result.error)
        _log.info("discovery done: %d labs, %d errors", len(self._labs), len(errors))
        return errors


#: Process-wide registry that the app populates with built-ins then `discover()`.
REGISTRY = LabRegistry()
