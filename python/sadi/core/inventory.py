"""Weight inventory as an event log: numbered weights, group balance weighing, combos.

Weights are entered once as `WeightSet` events (an edit is a later event for the same
number; history is kept). `GroupWeighed` events record the balance reading of a named
subset. `Inventory.reconcile` merges group and individual masses by generalised least
squares (the group reading is independent of the individual ones, so the posterior masses
become correlated); `Inventory.combo` then derives mass and stack height of any subset
with full-covariance propagation via `sadi.uncertainty`.
"""

# frob:ticket 01M6W7R26WGJ0TZ4GS8N0YH4FG

from __future__ import annotations

import math
from collections.abc import Sequence
from enum import StrEnum
from typing import Annotated, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError
from typani import Err, Ok, Result

from sadi.core.errors import ComputeCode, ComputeError, InputCode, InputError
from sadi.core.models import Quantity, Weight, WeightInventory
from sadi.logging_setup import get_logger
from sadi.uncertainty import CovarianceRegistry, Measured, first_order_variance

_log = get_logger(__name__)

#: |z| above which a group reading is flagged as inconsistent with the individual masses.
CONSISTENCY_Z = 2.0
_TIE_RTOL = 1e-9

Finite = Annotated[float, Field(allow_inf_nan=False)]
NonNeg = Annotated[float, Field(ge=0.0, allow_inf_nan=False)]
Pos = Annotated[float, Field(gt=0.0, allow_inf_nan=False)]


class _Frozen(BaseModel):
    """Base for immutable models; rejects unknown fields."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class WeightSet(_Frozen):
    """Event: weight `number` has this mass (kg) and height (m), each with 1-sigma uncertainty."""

    type: Literal["weight_set"] = "weight_set"
    number: int = Field(ge=1)
    mass: Pos
    u_mass: NonNeg
    height: NonNeg
    u_height: NonNeg


class GroupWeighed(_Frozen):
    """Event: the weights in `numbers` were weighed together on the balance (kg)."""

    type: Literal["group_weighed"] = "group_weighed"
    name: str = Field(min_length=1)
    numbers: tuple[int, ...] = Field(min_length=1)
    mass: Pos
    u_mass: NonNeg


Event = Annotated[WeightSet | GroupWeighed, Field(discriminator="type")]
_EVENT_ADAPTER: TypeAdapter[WeightSet | GroupWeighed] = TypeAdapter(Event)


def parse_event(text: str) -> Result[WeightSet | GroupWeighed, InputError]:
    """Parse one event from its JSON form (the WAL payload); Err(OUT_OF_RANGE) if invalid."""
    try:
        return Ok(_EVENT_ADAPTER.validate_json(text))
    except ValidationError as exc:
        _log.warning("bad inventory event: %s", exc.error_count())
        return Err(InputError(code=InputCode.OUT_OF_RANGE, detail=str(exc.errors()[0]["msg"])))


class MassSource(StrEnum):
    """Which estimate backs a combo mass."""

    INDIVIDUAL = "individual"
    GROUP = "group"
    COMBINED = "combined"


class MassChoice(_Frozen):
    """One candidate mass estimate for a combo and its standard uncertainty."""

    source: MassSource
    mass: float
    u_mass: float


class ConsistencyWarning(_Frozen):
    """A group reading that disagrees with the sum of its individual masses."""

    group: str
    difference: float
    u_difference: float
    z: float


class Reconciliation(_Frozen):
    """Posterior masses (kg) with their covariance, plus consistency warnings."""

    numbers: tuple[int, ...]
    masses: tuple[float, ...]
    covariance: tuple[tuple[float, ...], ...]
    warnings: tuple[ConsistencyWarning, ...] = ()


class Combo(_Frozen):
    """Derived mass and stack height of a subset, with the chosen mass estimate shown."""

    numbers: tuple[int, ...]
    mass: Quantity
    height: Quantity
    source: MassSource
    choices: tuple[MassChoice, ...]
    warnings: tuple[ConsistencyWarning, ...] = ()


def _cov_err(detail: str) -> ComputeError:
    """Build the DEGENERATE compute error for a failed reconciliation."""
    return ComputeError(code=ComputeCode.DEGENERATE, detail=detail)


def _sum_unc(
    means: Sequence[float],
    cov: Sequence[Sequence[float]],
    unit: str,
) -> Result[tuple[float, float], ComputeError]:
    """Sum quantities with the given covariance using sadi.uncertainty; return (value, u)."""
    reg = CovarianceRegistry()
    ms: list[Measured] = []
    for i, mean in enumerate(means):
        made = Measured.create(mean, math.sqrt(max(cov[i][i], 0.0)), unit, registry=reg)
        if isinstance(made, Err):
            return Err(_cov_err(str(made.danger_err)))
        ms.append(made.danger_ok)
    for i in range(len(ms)):
        for j in range(i + 1, len(ms)):
            bound = math.sqrt(
                reg.covariance(ms[i].id, ms[i].id) * reg.covariance(ms[j].id, ms[j].id)
            )
            c = max(-bound, min(bound, cov[i][j]))
            if c != 0.0:
                set_ = reg.set_covariance(ms[i].id, ms[j].id, c)
                if isinstance(set_, Err):
                    return Err(_cov_err(str(set_.danger_err)))
    var = first_order_variance(reg, [(m.id, 1.0) for m in ms])
    return Ok((sum(means), math.sqrt(max(var, 0.0))))


class Inventory(_Frozen):
    """Immutable event-sourced inventory; `record` returns a new inventory."""

    events: tuple[WeightSet | GroupWeighed, ...] = ()

    def weights(self) -> dict[int, WeightSet]:
        """Return the current entry of every weight number (latest event wins)."""
        out: dict[int, WeightSet] = {}
        for e in self.events:
            if isinstance(e, WeightSet):
                out[e.number] = e
        return out

    def groups(self) -> dict[str, GroupWeighed]:
        """Return the current group weighings by name (latest event wins)."""
        out: dict[str, GroupWeighed] = {}
        for e in self.events:
            if isinstance(e, GroupWeighed):
                out[e.name] = e
        return out

    def history(self, number: int) -> tuple[WeightSet, ...]:
        """Return every entry ever recorded for `number`, oldest first."""
        return tuple(e for e in self.events if isinstance(e, WeightSet) and e.number == number)

    def record(self, event: WeightSet | GroupWeighed) -> Result[Inventory, InputError]:
        """Append `event`; groups must name known, distinct weights. Returns the new inventory."""
        if isinstance(event, GroupWeighed):
            if len(set(event.numbers)) != len(event.numbers):
                _log.warning("group %s repeats a weight", event.name)
                return Err(InputError(code=InputCode.DUPLICATE, detail=event.name))
            known = self.weights()
            for n in event.numbers:
                if n not in known:
                    _log.warning("group %s names unknown weight %d", event.name, n)
                    return Err(InputError(code=InputCode.UNKNOWN_ID, detail=str(n)))
            _log.info("group %s weighed: %s = %g kg", event.name, event.numbers, event.mass)
        else:
            kind = "edited" if event.number in self.weights() else "entered"
            _log.info("weight %d %s: %g kg, %g m", event.number, kind, event.mass, event.height)
        return Ok(Inventory(events=(*self.events, event)))

    def reconcile(self) -> Result[Reconciliation, ComputeError]:
        """Merge group readings with individual masses (generalised least squares)."""
        ws = self.weights()
        numbers = tuple(sorted(ws))
        idx = {n: i for i, n in enumerate(numbers)}
        m = np.array([ws[n].mass for n in numbers], dtype=float)
        v0 = np.diag([ws[n].u_mass ** 2 for n in numbers])
        groups = list(self.groups().values())
        warnings: list[ConsistencyWarning] = []
        if not groups:
            _log.debug("reconcile: no groups, %d individual weights", len(numbers))
            return Ok(_recon(numbers, m, v0, warnings))
        a = np.zeros((len(groups), len(numbers)))
        for r, g in enumerate(groups):
            for n in g.numbers:
                a[r, idx[n]] = 1.0
        gm = np.array([g.mass for g in groups], dtype=float)
        r_cov = np.diag([g.u_mass**2 for g in groups])
        resid = gm - a @ m
        s = a @ v0 @ a.T + r_cov
        for r, g in enumerate(groups):
            u_diff = math.sqrt(float(s[r, r]))
            z = float(resid[r]) / u_diff if u_diff > 0 else 0.0
            if abs(z) > CONSISTENCY_Z:
                _log.warning("group %s inconsistent with individuals: z=%.2f", g.name, z)
                warnings.append(
                    ConsistencyWarning(
                        group=g.name, difference=float(resid[r]), u_difference=u_diff, z=z
                    )
                )
        try:
            k = np.linalg.solve(s, a @ v0).T
        except np.linalg.LinAlgError:
            _log.error("reconcile: singular group system")
            return Err(_cov_err("group readings are exact and redundant"))
        post_m = m + k @ resid
        post_v = v0 - k @ a @ v0
        post_v = (post_v + post_v.T) / 2.0
        if not (np.all(np.isfinite(post_m)) and np.all(np.isfinite(post_v))):
            return Err(ComputeError(code=ComputeCode.NOT_FINITE, detail="reconciliation"))
        _log.info("reconciled %d weights with %d groups", len(numbers), len(groups))
        return Ok(_recon(numbers, post_m, post_v, warnings))

    def combo(self, weight_ids: Sequence[int]) -> Result[Combo, InputError | ComputeError]:
        """Return mass and stack height of the weights `weight_ids`, choosing the best mass."""
        ids = tuple(weight_ids)
        if not ids:
            return Err(InputError(code=InputCode.MISSING, detail="no weights"))
        if len(set(ids)) != len(ids):
            return Err(InputError(code=InputCode.DUPLICATE, detail=str(ids)))
        ws = self.weights()
        for n in ids:
            if n not in ws:
                _log.warning("combo: unknown weight %d", n)
                return Err(InputError(code=InputCode.UNKNOWN_ID, detail=str(n)))
        rec = self.reconcile()
        if isinstance(rec, Err):
            return Err(rec.danger_err)
        r = rec.danger_ok
        pos = {n: i for i, n in enumerate(r.numbers)}
        sel = [pos[n] for n in ids]
        post = _sum_unc(
            [r.masses[i] for i in sel], [[r.covariance[i][j] for j in sel] for i in sel], "kg"
        )
        ind = _sum_unc(
            [ws[n].mass for n in ids],
            [[ws[a].u_mass ** 2 if a == b else 0.0 for b in ids] for a in ids],
            "kg",
        )
        hts = _sum_unc(
            [ws[n].height for n in ids],
            [[ws[a].u_height ** 2 if a == b else 0.0 for b in ids] for a in ids],
            "m",
        )
        for res in (post, ind, hts):
            if isinstance(res, Err):
                return Err(res.danger_err)
        choices = [
            MassChoice(source=MassSource.INDIVIDUAL, mass=ind.danger_ok[0], u_mass=ind.danger_ok[1])
        ]
        wanted = set(ids)
        for g in self.groups().values():
            if set(g.numbers) == wanted:
                choices.append(MassChoice(source=MassSource.GROUP, mass=g.mass, u_mass=g.u_mass))
        choices.append(
            MassChoice(source=MassSource.COMBINED, mass=post.danger_ok[0], u_mass=post.danger_ok[1])
        )
        best = choices[0]
        for c in choices[1:]:
            if c.u_mass < best.u_mass * (1 - _TIE_RTOL):
                best = c
        _log.info(
            "combo %s: %s mass %g +/- %g kg (individual %g, combined %g)",
            ids,
            best.source,
            best.mass,
            best.u_mass,
            choices[0].u_mass,
            choices[-1].u_mass,
        )
        involved = {n for g in self.groups().values() for n in g.numbers if n in wanted}
        warns = tuple(w for w in r.warnings if involved and self._group_touches(w.group, wanted))
        return Ok(
            Combo(
                numbers=ids,
                mass=Quantity(value=best.mass, standard_uncertainty=best.u_mass, unit="kg"),
                height=Quantity(
                    value=hts.danger_ok[0], standard_uncertainty=hts.danger_ok[1], unit="m"
                ),
                source=best.source,
                choices=tuple(choices),
                warnings=warns,
            )
        )

    def _group_touches(self, name: str, wanted: set[int]) -> bool:
        """Return True if group `name` shares a weight with `wanted`."""
        return bool(wanted & set(self.groups()[name].numbers))

    def to_weight_inventory(self) -> Result[WeightInventory, InputError | ComputeError]:
        """Export reconciled masses as the core `WeightInventory` (ids are the numbers)."""
        rec = self.reconcile()
        if isinstance(rec, Err):
            return Err(rec.danger_err)
        r = rec.danger_ok
        ws = self.weights()
        out: list[Weight] = []
        for i, n in enumerate(r.numbers):
            if r.masses[i] <= 0.0:
                return Err(InputError(code=InputCode.OUT_OF_RANGE, detail=f"weight {n} mass"))
            out.append(
                Weight(
                    id=str(n),
                    mass=r.masses[i],
                    u_mass=math.sqrt(max(r.covariance[i][i], 0.0)),
                    height=ws[n].height,
                    u_height=ws[n].u_height,
                )
            )
        return Ok(WeightInventory(weights=tuple(out)))


def _recon(
    numbers: tuple[int, ...],
    masses: np.ndarray,
    cov: np.ndarray,
    warnings: list[ConsistencyWarning],
) -> Reconciliation:
    """Pack numpy results into the frozen Reconciliation model."""
    return Reconciliation(
        numbers=numbers,
        masses=tuple(float(x) for x in masses),
        covariance=tuple(tuple(float(x) for x in row) for row in cov),
        warnings=tuple(warnings),
    )
