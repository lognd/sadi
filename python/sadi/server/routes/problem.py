"""problem+json (RFC 7807) mapping: every typed error becomes one ApiProblem with a hint."""

# frob:ticket 01M6W7R3XY1B0BF689RX3H80G2

from __future__ import annotations

import re
from typing import TypeVar

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from typani import ErrorSet, Result

from sadi.core.errors import SadiError
from sadi.core.wizard import WizardError
from sadi.logging_setup import get_logger

_log = get_logger(__name__)

PROBLEM_MEDIA_TYPE = "application/problem+json"
_T = TypeVar("_T")

#: HTTP status per wizard refusal; anything absent is a 409 (state conflict).
_WIZARD_STATUS: dict[WizardError, int] = {
    WizardError.NoSteps: 500,
    WizardError.DuplicateStep: 500,
    WizardError.UnknownStep: 404,
    WizardError.UnknownPoint: 404,
    WizardError.BadEdit: 422,
    WizardError.BadWindow: 422,
    WizardError.BadInput: 422,
    WizardError.PhaseMismatch: 422,
}

#: HTTP status per session/store error class name; anything absent is a 500.
_STORE_STATUS: dict[str, int] = {
    "Locked": 409,
    "RootLockFailed": 409,
    "BadSessionName": 422,
    "NotASession": 404,
    "ParentIncomplete": 409,
    "ParentCorrupt": 409,
    "ProvenanceMismatch": 409,
    "Backpressure": 503,
    "Stalled": 503,  # frob:ticket 01M72YKEWHJJXEBBV7XDP5Z31J
    "Closed": 409,
}


class ApiProblem(BaseModel):
    """RFC 7807 body: stable `type`, human `title`/`detail` and a 'what to do' `hint`."""

    model_config = ConfigDict(frozen=True)
    type: str
    title: str
    status: int
    detail: str = ""
    hint: str = ""


class ProblemError(Exception):
    """Raised by `unwrap` so the app-level handler renders the problem; never business logic."""

    def __init__(self, problem: ApiProblem) -> None:
        """Carry the already-built `problem`."""
        super().__init__(problem.title)
        self.problem = problem


def _snake(name: str) -> str:
    """CamelCase class name to snake_case wire code."""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def from_sadi(err: SadiError) -> ApiProblem:
    """Map a taxonomy error (family, code, hint, status) to a problem."""
    return ApiProblem.model_validate(err.problem())


def from_wizard(err: ErrorSet) -> ApiProblem:
    """Map a WizardError member; its description is the hint to show."""
    code = _snake(err.name)
    status = _WIZARD_STATUS.get(err, 409) if isinstance(err, WizardError) else 409
    return ApiProblem(
        type=f"urn:sadi:error:wizard:{code}",
        title=code.replace("_", " "),
        status=status,
        detail=err.description,
        hint=err.description,
    )


def from_model(err: BaseModel, family: str) -> ApiProblem:
    """Map a pydantic session/writer/replay error (has an optional `hint`) to a problem."""
    name = type(err).__name__
    hint = str(getattr(err, "hint", "") or "") or "See the server log for details."
    return ApiProblem(
        type=f"urn:sadi:error:{family}:{_snake(name)}",
        title=_snake(name).replace("_", " "),
        status=_STORE_STATUS.get(name, 500),
        detail=repr(err)[:300],
        hint=hint,
    )


def not_found(what: str, hint: str) -> ApiProblem:
    """A 404 for a missing resource, with the hint saying how to pick an existing one."""
    return ApiProblem(
        type="urn:sadi:error:input:unknown_id",
        title="unknown id",
        status=404,
        detail=what,
        hint=hint,
    )


def conflict(code: str, detail: str, hint: str) -> ApiProblem:
    """A 409 for an action the current server state does not allow."""
    return ApiProblem(
        type=f"urn:sadi:error:state:{code}",
        title=code.replace("_", " "),
        status=409,
        detail=detail,
        hint=hint,
    )


def unwrap(result: Result[_T, ApiProblem]) -> _T:
    """Return the Ok value or raise `ProblemError` for the app handler to render."""
    if result.is_err:
        raise ProblemError(result.danger_err)
    return result.danger_ok


def render(problem: ApiProblem) -> JSONResponse:
    """Build the application/problem+json response for `problem`."""
    _log.warning("problem %s (%d): %s", problem.type, problem.status, problem.detail)
    return JSONResponse(
        status_code=problem.status,
        content=problem.model_dump(),
        media_type=PROBLEM_MEDIA_TYPE,
    )


def install_problem_handlers(app: FastAPI) -> None:
    """Register the `ProblemError` handler that renders application/problem+json."""

    @app.exception_handler(ProblemError)
    async def _handle(_request: Request, exc: ProblemError) -> JSONResponse:
        """Render a raised ProblemError."""
        return render(exc.problem)

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(_request: Request, exc: RequestValidationError) -> JSONResponse:
        """Render a malformed request as a 422 problem naming the first offending field."""
        first = exc.errors()[0] if exc.errors() else {}
        where = ".".join(str(x) for x in first.get("loc", ()))
        return render(
            ApiProblem(
                type="urn:sadi:error:input:invalid",
                title="invalid",
                status=422,
                detail=f"{where}: {first.get('msg', 'invalid request')}",
                hint="Correct the named field and send the request again.",
            )
        )
