"""LCTT live recompute: all results from the raw event stream after every captured point."""

# frob:ticket 01M6W7R3J00J2HQ7XPW19WDD6Q

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field
from typani import Err, ErrorSet, Ok, Result

from sadi.core.results import ResultSet, ResultValue, make_result
from sadi.labs.lctt.calibration import CalibrationFit, fit_calibration
from sadi.labs.lctt.loading import (
    LoadingInputs,
    LoadingOptions,
    LoadingResult,
    compute_loading,
    pool_tare,
)
from sadi.labs.lctt.modulus import CurvePoint, ModulusFit, fit_modulus, suggest_window
from sadi.labs.lctt.yield_ import YieldResult, find_yield
from sadi.logging_setup import get_logger
from sadi.uncertainty import Measured, Provenance

_log = get_logger(__name__)

#: Results whose heavy refinement (Monte Carlo cross-check) is delegated to jobs (J3).
REFINED = ("E", "yield_stress")


class LiveError(ErrorSet):
    """Live recompute failure; the description says what to fix."""

    UnknownPoint = "An edit names a point id that was never captured"
    DuplicatePoint = "Two captured points share one point id"
    BadInput = "An event carries a value the engine cannot represent"


class _Ev(BaseModel):
    """Frozen base for all live events."""

    model_config = ConfigDict(frozen=True)


class CalPoint(_Ev):
    """One calibration sample: LVDT volts at a known height (m)."""

    kind: Literal["cal"] = "cal"
    volts: float
    height: float


class TareBlock(_Ev):
    """One tare block of raw voltage readings summarised as mean, sample sd and count."""

    kind: Literal["tare"] = "tare"
    mean: float
    sd: float
    n: int


class SpecimenSetup(_Ev):
    """Specimen and hanger geometry/mass in SI with their standard uncertainties."""

    kind: Literal["specimen"] = "specimen"
    diameter: float
    u_diameter: float = 0.0
    hanger_kg: float = 0.0
    u_hanger_kg: float = 0.0


class LoadPoint(_Ev):
    """A captured point from RAW values: block-mean volts and total hanging mass (kg)."""

    kind: Literal["point"] = "point"
    point_id: str
    volts: float
    u_volts: float = 0.0
    mass_kg: float
    u_mass_kg: float = 0.0
    # frob:ticket 01M6WP144S0ENPQESCQEQ6NT5Y
    settled: bool = False
    forced_early: bool = False
    drift_rate: float | None = None
    t_since_load_s: float | None = None
    # frob:ticket 01M6WX3GGD2VSGEY1GT2X49DSV
    volts_sd: float | None = None  # per-sample std dev of the raw volts in the window
    # frob:ticket 01M729642YCP4MRYBWBNQBYW7A
    phase: str = ""  # "elastic" / "plastic" (selects specimen L0); "" = unknown (legacy)


class OverridePoint(_Ev):
    """Review edit: replace the raw volts and/or mass of a captured point."""

    kind: Literal["override"] = "override"
    point_id: str
    volts: float | None = None
    mass_kg: float | None = None


class ExcludePoint(_Ev):
    """Review edit: exclude (or re-include) a point from every fit."""

    kind: Literal["exclude"] = "exclude"
    point_id: str
    excluded: bool = True


class SetWindow(_Ev):
    """Review edit: E fit window as inclusive indices among the active points."""

    kind: Literal["window"] = "window"
    first: int
    last: int


LiveEvent = Annotated[
    CalPoint | TareBlock | SpecimenSetup | LoadPoint | OverridePoint | ExcludePoint | SetWindow,
    Field(discriminator="kind"),
]


class LiveConfig(BaseModel):
    """Recompute options: loading options, offset-yield strain and readout target."""

    model_config = ConfigDict(frozen=True)

    loading: LoadingOptions = LoadingOptions()
    offset: float = 0.002
    target: float = 0.05


class _State(BaseModel):
    """Folded event history (raw-derived inputs only)."""

    cal: list[CalPoint] = []
    tare: list[TareBlock] = []
    specimen: SpecimenSetup | None = None
    points: dict[str, LoadPoint] = {}
    excluded: set[str] = set()
    window: SetWindow | None = None


class LoadCache:
    """Memo of per-point loading results so an update only computes the new point."""

    def __init__(self) -> None:
        """Start empty."""
        self._data: dict[tuple[float, ...], LoadingResult] = {}

    def get(self, key: tuple[float, ...]) -> LoadingResult | None:
        """Return the cached loading result for `key`, if any."""
        return self._data.get(key)

    def put(self, key: tuple[float, ...], value: LoadingResult) -> None:
        """Store a loading result under `key`."""
        self._data[key] = value


def _fold(events: Sequence[LiveEvent]) -> Result[_State, LiveError]:
    """Replay events in order into a _State; edits must name known points."""
    st = _State()
    for ev in events:
        if isinstance(ev, CalPoint):
            st.cal.append(ev)
        elif isinstance(ev, TareBlock):
            st.tare.append(ev)
        elif isinstance(ev, SpecimenSetup):
            st.specimen = ev
        elif isinstance(ev, LoadPoint):
            if ev.point_id in st.points:
                _log.warning("fold: duplicate point id %s", ev.point_id)
                return Err(LiveError.DuplicatePoint)
            st.points[ev.point_id] = ev
        elif isinstance(ev, SetWindow):
            st.window = ev
        else:
            cur = st.points.get(ev.point_id)
            if cur is None:
                _log.warning("fold: edit for unknown point %s", ev.point_id)
                return Err(LiveError.UnknownPoint)
            if isinstance(ev, ExcludePoint):
                (st.excluded.add if ev.excluded else st.excluded.discard)(ev.point_id)
            else:
                upd = {
                    k: v for k, v in (("volts", ev.volts), ("mass_kg", ev.mass_kg)) if v is not None
                }
                st.points[ev.point_id] = cur.model_copy(update=upd)
    return Ok(st)


def _measured(v: float, u: float, unit: str, src: str) -> Result[Measured, LiveError]:
    """Build a Measured or report BadInput."""
    made = Measured.create(v, u, unit, provenance=Provenance(source=src))
    if isinstance(made, Err):
        _log.warning("measured %s failed: %s", src, made.danger_err)
        return Err(LiveError.BadInput)
    return Ok(made.danger_ok)


def _curve(  # noqa: PLR0913
    st: _State,
    slope: Measured,
    tare: Measured,
    spec: SpecimenSetup,
    cfg: LiveConfig,
    cache: LoadCache,
) -> Result[list[CurvePoint], LiveError]:
    """Stress/strain curve of the active points, using the cache for unchanged points."""
    dia = _measured(spec.diameter, spec.u_diameter, "m", "diameter")
    hang = _measured(spec.hanger_kg, spec.u_hanger_kg, "kg", "hanger")
    if isinstance(dia, Err) or isinstance(hang, Err):
        return Err(LiveError.BadInput)
    out: list[CurvePoint] = []
    for pid, p in st.points.items():
        if pid in st.excluded:
            continue
        key = (
            p.volts, p.u_volts, p.mass_kg, p.u_mass_kg, slope.value, slope.std_unc,
            tare.value, tare.std_unc, spec.diameter, spec.u_diameter, spec.hanger_kg,
            spec.u_hanger_kg, cfg.loading.gauge_length,
        )  # fmt: skip
        res = cache.get(key)
        if res is None:
            volt = _measured(p.volts, p.u_volts, "V", "volts")
            mass = _measured(p.mass_kg, p.u_mass_kg, "kg", "mass")
            if isinstance(volt, Err) or isinstance(mass, Err):
                return Err(LiveError.BadInput)
            inputs = LoadingInputs(
                voltage=volt.danger_ok, tare=tare, slope=slope, masses=(mass.danger_ok,),
                hanger=hang.danger_ok, diameter=dia.danger_ok,
            )  # fmt: skip
            loaded = compute_loading(inputs, cfg.loading)
            if isinstance(loaded, Err):
                _log.warning("curve: loading failed for %s: %s", pid, loaded.danger_err)
                return Err(LiveError.BadInput)
            res = loaded.danger_ok
            cache.put(key, res)
        out.append(CurvePoint(index=len(out), stress=res.stress, strain=res.strain))
    return Ok(out)


def _add(
    vals: list[ResultValue], notes: list[str], name: str, m: Measured, unit: str, cfg: LiveConfig
) -> None:
    """Append the readout of a Measured to `vals`, noting a failure instead of raising."""
    made = make_result(name, m.value, m.std_unc, unit, dof=m.dof, target=cfg.target)
    if isinstance(made, Err):
        notes.append(f"{name}: {made.danger_err}")
    else:
        vals.append(made.danger_ok)


def recompute(
    events: Sequence[LiveEvent],
    config: LiveConfig | None = None,
    *,
    cache: LoadCache | None = None,
) -> Result[ResultSet, LiveError]:
    """Recompute every result from RAW events (never cached display values); pure and sync.

    Analytic RSS only: Monte Carlo is requested via `ResultSet.refinement` for a job (J3).
    """
    cfg = config or LiveConfig()
    memo = cache if cache is not None else LoadCache()
    folded = _fold(events)
    if isinstance(folded, Err):
        return Err(folded.danger_err)
    st = folded.danger_ok
    vals: list[ResultValue] = []
    notes: list[str] = []
    pending: list[str] = []
    n_active = len(st.points) - len(st.excluded)

    cal: CalibrationFit | None = None
    fitted = fit_calibration([c.volts for c in st.cal], [c.height for c in st.cal])
    if isinstance(fitted, Ok):
        cal = fitted.danger_ok
        _add(vals, notes, "slope", cal.slope, "m/V", cfg)
        _add(vals, notes, "intercept", cal.intercept, "m", cfg)
        r2 = make_result("calibration_r2", cal.r2, 0.0, "1", target=cfg.target)
        if isinstance(r2, Ok):
            vals.append(r2.danger_ok)
    else:
        pending += ["slope", "intercept"]
        notes.append(f"calibration: {fitted.danger_err}")

    tare: Measured | None = None
    if st.tare:
        pooled = pool_tare(
            [t.mean for t in st.tare], [t.sd for t in st.tare], [t.n for t in st.tare]
        )
        if isinstance(pooled, Ok):
            tare = pooled.danger_ok
            _add(vals, notes, "tare", tare, "V", cfg)
        else:
            notes.append(f"tare: {pooled.danger_err}")
    if tare is None:
        pending.append("tare")

    if cal is None or tare is None or st.specimen is None or n_active == 0:
        pending += ["E", "r2", "yield_stress"]
        _log.debug("recompute: waiting for inputs (%d active points)", n_active)
        return Ok(_finish(vals, pending, notes, n_active))

    curve = _curve(st, cal.slope, tare, st.specimen, cfg, memo)
    if isinstance(curve, Err):
        return Err(curve.danger_err)
    _fit_and_yield(curve.danger_ok, st, cfg, vals, notes, pending)
    return Ok(_finish(vals, pending, notes, n_active))


def _e_window(curve: list[CurvePoint], window: SetWindow | None) -> tuple[int, int]:
    """Pick the E window: an explicit one wins, else the auto linear window, else all points."""
    # frob:ticket 01M6X00779KYJW2VFKEEQ9QEP7
    if window is not None:
        return window.first, window.last
    auto = suggest_window(curve)
    if isinstance(auto, Ok):
        _log.info("recompute: auto E window %d..%d of %d points", *auto.danger_ok, len(curve))
        return auto.danger_ok
    _log.info("recompute: no auto E window; fitting all %d points", len(curve))
    return 0, len(curve) - 1


def _fit_and_yield(  # noqa: PLR0913
    curve: list[CurvePoint],
    st: _State,
    cfg: LiveConfig,
    vals: list[ResultValue],
    notes: list[str],
    pending: list[str],
) -> None:
    """Fit E over the chosen window, then yield; unavailable pieces become pending."""
    first, last = _e_window(curve, st.window)
    fit = fit_modulus(curve, first, last)
    if isinstance(fit, Err):
        notes.append(f"E: {fit.danger_err}")
        pending += ["E", "r2", "yield_stress"]
        return
    mf: ModulusFit = fit.danger_ok
    _add(vals, notes, "E", mf.modulus, "Pa", cfg)
    r2 = make_result("r2", mf.r2, 0.0, "1", target=cfg.target)
    if isinstance(r2, Ok):
        vals.append(r2.danger_ok)
    if mf.low_r2:
        notes.append(f"E: r^2 {mf.r2:.4f} is below the threshold; check the window")
    if mf.saturated_points:
        notes.append(f"E: saturated points in window: {mf.saturated_points}")
    yld = find_yield(curve, mf.modulus, cfg.offset)
    if isinstance(yld, Err):
        pending.append("yield_stress")
        notes.append(f"yield: {yld.danger_err}")
        return
    y: YieldResult = yld.danger_ok
    _add(vals, notes, "yield_stress", y.yield_stress, "Pa", cfg)


def _finish(vals: list[ResultValue], pending: list[str], notes: list[str], n: int) -> ResultSet:
    """Assemble the ResultSet and name the results a job should refine."""
    done = {v.name for v in vals}
    return ResultSet(
        n_points=n,
        values=tuple(vals),
        pending=tuple(pending),
        notes=tuple(notes),
        refinement=tuple(r for r in REFINED if r in done),
    )


class LiveEngine:
    """Incremental front end: append events, get the updated ResultSet (equals batch)."""

    def __init__(self, config: LiveConfig | None = None) -> None:
        """Start with no events and a fresh per-point cache."""
        self._cfg = config or LiveConfig()
        self._events: list[LiveEvent] = []
        self._cache = LoadCache()

    @property
    def events(self) -> tuple[LiveEvent, ...]:
        """The raw event history so far."""
        return tuple(self._events)

    def add(self, event: LiveEvent) -> Result[ResultSet, LiveError]:
        """Append one event and recompute; a rejected event is not kept."""
        self._events.append(event)
        out = recompute(self._events, self._cfg, cache=self._cache)
        if isinstance(out, Err):
            self._events.pop()
            _log.warning("engine: event rejected: %s", out.danger_err)
        return out
