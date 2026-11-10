"""Read-only doctor routes: GET /api/doctor and POST /api/doctor/{check_id}/run."""

# frob:ticket 01M6WKJKCYJ3PQG2DEX16R80J2

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from typani import Err, Ok

from sadi.doctor import run
from sadi.doctor.registry import all_checks
from sadi.doctor.schema import CheckResult, DoctorError, DoctorReport, RunOptions
from sadi.logging_setup import get_logger

_log = get_logger(__name__)


def _raise_http(err: DoctorError, what: str) -> HTTPException:
    """Map a DoctorError to a typed HTTP error (unknown id/layer -> 404)."""
    _log.info("doctor %s -> 404 (%s)", what, err.name)
    return HTTPException(status_code=404, detail=err.description)


def make_doctor_router(data_root: Path | None = None) -> APIRouter:
    """Build the doctor router for `data_root`; checks run in a threadpool, read-only."""
    root = str(data_root) if data_root is not None else None
    router = APIRouter(prefix="/api/doctor", tags=["doctor"])

    @router.get("", response_model=DoctorReport)
    async def get_doctor() -> DoctorReport:
        """Run every check and return the full DoctorReport."""
        res = await run_in_threadpool(run, RunOptions(data_root=root, probe_device=False))
        if isinstance(res, Err):
            raise _raise_http(res.error, "GET")
        assert isinstance(res, Ok)
        return res.value

    @router.post("/{check_id}/run", response_model=CheckResult)
    async def run_check(check_id: str) -> CheckResult:
        """Re-run one check and return its CheckResult, or 404 for an unknown id."""
        # Validate the id against the catalog first: RunOptions constrains the id pattern.
        if check_id not in {spec.id for spec, _ in all_checks()}:
            _log.info("doctor POST %r -> 404 (unknown check)", check_id)
            raise HTTPException(status_code=404, detail=DoctorError.UnknownCheck.description)
        # frob:ticket 01M72D3CTDED2MGDY721RSM8M4
        # probe_device=False: a re-run must not open the port a live driver owns.
        opts = RunOptions(checks=(check_id,), data_root=root, probe_device=False)
        res = await run_in_threadpool(run, opts)
        if isinstance(res, Err):
            raise _raise_http(res.error, "POST")
        assert isinstance(res, Ok)
        return res.value.results[0]

    return router
