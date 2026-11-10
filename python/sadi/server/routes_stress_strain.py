"""Read-only refit route: POST /api/stress-strain/fit {first, last} -> ModulusFitView."""

# frob:ticket 01M6WMSZKN488HTWG19V69GETD

from __future__ import annotations

from collections.abc import Callable, Sequence

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from typani import Err, ErrorSet, Ok, Result

from sadi.labs.lctt.calibration import fit_calibration
from sadi.labs.lctt.modulus import CurvePoint, ModulusError, ModulusFit, fit_modulus
from sadi.logging_setup import get_logger
from sadi.synthetic.provenance import REAL, DataProvenance

_log = get_logger(__name__)

PA_PER_MPA = 1e6
PA_PER_GPA = 1e9


class RefitError(ErrorSet):
    """Server-side refit failure that is not a ModulusError."""

    NoData = "No stress-strain data is available to refit; record or open a session first"
    NoOpenSession = "no_open_session: open or resume a session before refitting"
    Intercept = "The fit intercept could not be computed for this window"


class FitWindowRequest(BaseModel):
    """Request body: inclusive point-index window of the active (non-excluded) curve."""

    model_config = ConfigDict(frozen=True)
    first: int
    last: int


class ModulusFitView(BaseModel):
    """Response matching the web client's ModulusFitView (MPa for the line, GPa for E)."""

    model_config = ConfigDict(frozen=True)
    first: int
    last: int
    modulusMpa: float  # noqa: N815 - wire name fixed by the web client
    interceptMpa: float  # noqa: N815
    display: str
    eGpa: float  # noqa: N815
    eU95Gpa: float  # noqa: N815
    r2: float
    lowR2: bool  # noqa: N815
    provenance: DataProvenance = REAL  # frob:ticket 01M71SYG3H3X7GJT21TE6MY8YC


class ErrorBody(BaseModel):
    """4xx body the client can display: a stable `error` code and a `detail` hint."""

    error: str
    detail: str


# Reads the stored curve fresh on every call; never writes.
CurveSource = Callable[[], Result[Sequence[CurvePoint], RefitError]]


def to_view(fit: ModulusFit, intercept_pa: float) -> ModulusFitView:
    """Convert a ModulusFit (SI) to the client view (MPa line, GPa E and U95)."""
    e_gpa, u_gpa = fit.modulus.value / PA_PER_GPA, fit.u95 / PA_PER_GPA
    return ModulusFitView(
        first=fit.first,
        last=fit.last,
        modulusMpa=fit.modulus.value / PA_PER_MPA,
        interceptMpa=intercept_pa / PA_PER_MPA,
        display=f"E = {e_gpa:.2f} +/- {u_gpa:.2f} GPa, r^2 = {fit.r2:.4f}",
        eGpa=e_gpa,
        eU95Gpa=u_gpa,
        r2=fit.r2,
        lowR2=fit.low_r2,
    )


def refit(
    points: Sequence[CurvePoint], first: int, last: int
) -> Result[ModulusFitView, ModulusError | RefitError]:
    """Refit E over points[first..last] with the existing analysis code (pure, no writes)."""
    res = fit_modulus(points, first, last)
    if not isinstance(res, Ok):
        return Err(res.unwrap_err())
    fit = res.value
    win = points[first : last + 1]
    cal = fit_calibration([p.strain.value for p in win], [p.stress.value for p in win])
    if not isinstance(cal, Ok):
        _log.error("refit: intercept fit failed: %s", cal.unwrap_err().name)
        return Err(RefitError.Intercept)
    return Ok(to_view(fit, cal.value.intercept.value))


def _status(error: ModulusError | RefitError) -> int:
    """HTTP status for a refit error: bad window 422, no data 409, others 422/500."""
    if error is ModulusError.BadWindow:
        return 422
    if error in (RefitError.NoData, RefitError.NoOpenSession):
        return 409
    if error in (ModulusError.Fit, ModulusError.NoWindow):
        return 422
    return 500


def make_stress_strain_router(
    source: CurveSource | None = None,
    provenance: DataProvenance | Callable[[], DataProvenance] = REAL,
) -> APIRouter:
    """Build the router; `source` supplies stored curve points (None -> 409 NoData).

    `provenance` may be a callable so the stamp follows the open session.
    """
    router = APIRouter(prefix="/api/stress-strain", tags=["stress-strain"])

    def _fail(error: ModulusError | RefitError) -> JSONResponse:
        status = _status(error)
        _log.info("stress-strain fit -> %d (%s)", status, error.name)
        body = ErrorBody(error=error.name, detail=error.description)
        return JSONResponse(status_code=status, content=body.model_dump())

    @router.post("/fit", response_model=ModulusFitView, responses={"4XX": {"model": ErrorBody}})
    async def post_fit(req: FitWindowRequest) -> ModulusFitView | JSONResponse:
        """Recompute E, r^2 and U95 over the window from stored data; read-only."""
        if source is None:
            return _fail(RefitError.NoData)
        loaded = await run_in_threadpool(source)
        if not isinstance(loaded, Ok):
            return _fail(loaded.unwrap_err())
        res = await run_in_threadpool(refit, loaded.value, req.first, req.last)
        if not isinstance(res, Ok):
            return _fail(res.unwrap_err())
        stamp = provenance() if callable(provenance) else provenance  # frob:ticket 01M72V8SNA08E3QD12A1TSFDV3
        return res.value.model_copy(update={"provenance": stamp})

    return router
