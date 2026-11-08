"""LCTT specimen specs: the long (elastic) and short (plastic) wires and their gauge lengths."""

# frob:ticket 01M6W7R3RXWS1WSH3TPXMK16Q2

from __future__ import annotations

import math
from enum import StrEnum

from pydantic import BaseModel, ConfigDict
from typani import Err, ErrorSet, Ok, Result

from sadi.labs.lctt.loading import LONG_L0_M, SHORT_L0_M, LoadingOptions, Specimen
from sadi.logging_setup import get_logger

_log = get_logger(__name__)


class SpecimenError(ErrorSet):
    """Specimen spec failure; the description says what to fix."""

    BadLength = "Gauge length L0 must be finite and > 0 metres; enter a real length"


class SpecimenRole(StrEnum):
    """What a specimen is run for: the long wire gives E, the short wire gives yield."""

    ELASTIC = "elastic"
    PLASTIC = "plastic"


class SpecimenSpec(BaseModel):
    """One specimen: its role, optional label and gauge length (default by role, editable)."""

    model_config = ConfigDict(frozen=True)

    role: SpecimenRole
    label: str = ""
    l0: float | None = None

    @property
    def kind(self) -> Specimen:
        """The loading specimen kind for this role (long for elastic, short for plastic)."""
        return Specimen.LONG if self.role is SpecimenRole.ELASTIC else Specimen.SHORT

    @property
    def l0_m(self) -> float:
        """Effective gauge length in metres: the edit when set, else the role default."""
        if self.l0 is not None:
            return self.l0
        return LONG_L0_M if self.role is SpecimenRole.ELASTIC else SHORT_L0_M

    @property
    def name(self) -> str:
        """Human source name used in results: the label, else the role and gauge length."""
        return self.label or f"{self.role.value} specimen (L0 {self.l0_m:g} m)"

    def loading_options(self) -> LoadingOptions:
        """Loading options carrying this specimen's kind and gauge length."""
        return LoadingOptions(specimen=self.kind, l0=self.l0_m)


def make_spec(
    role: SpecimenRole, *, l0: float | None = None, label: str = ""
) -> Result[SpecimenSpec, SpecimenError]:
    """Build a spec, rejecting a non-finite or non-positive L0 override."""
    if l0 is not None and not (math.isfinite(l0) and l0 > 0):
        _log.warning("make_spec: rejected L0 %r for %s", l0, role)
        return Err(SpecimenError.BadLength)
    _log.info("make_spec: %s L0=%s", role, l0 if l0 is not None else "default")
    return Ok(SpecimenSpec(role=role, label=label, l0=l0))


def with_l0(spec: SpecimenSpec, l0: float) -> Result[SpecimenSpec, SpecimenError]:
    """Return `spec` with an edited gauge length (long default 0.5 m is editable)."""
    return make_spec(spec.role, l0=l0, label=spec.label)
