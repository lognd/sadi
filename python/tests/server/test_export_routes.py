"""Export routes over the real app: format listing, CSV download, figure JSON, problems."""

# frob:ticket 01M6WTCA3WJA26T204SWR6VW70

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel
from typani import Err, Ok, Result

from sadi.core.errors import ComputeCode, ComputeError
from sadi.core.lab import (
    AnalysisResult,
    ExportFormat,
    ExportFormatId,
    LabId,
    StepSpec,
)
from sadi.core.models import CapturedPoint, RunState
from sadi.core.registry import LabRegistry
from sadi.labs.lctt.plugin import register
from sadi.server.app import AppSettings, create_app


def _csv(run: RunState, res: AnalysisResult) -> Result[bytes, ComputeError]:
    return Ok(f"session,points\n{run.session_id},{len(run.points)}\n".encode("ascii"))


def _fig(run: RunState, res: AnalysisResult) -> Result[bytes, ComputeError]:
    return Ok(json.dumps({"x": [1, 2], "y": [3, 4]}).encode("ascii"))


def _bad(run: RunState, res: AnalysisResult) -> Result[bytes, ComputeError]:
    return Err(ComputeError(code=ComputeCode.TOO_FEW_POINTS, detail="need 2"))


def _fmt(fid: str, media: str, writer) -> ExportFormat:  # noqa: ANN001
    return ExportFormat(id=ExportFormatId(fid), title=fid, media_type=media, writer=writer)


class ExportLab:
    """The lctt steps with three export formats; recompute is empty."""

    id = LabId("exp")
    title = "Export lab"
    models: tuple[type[BaseModel], ...] = ()

    def __init__(self) -> None:
        """Declare the formats per instance (the protocol attribute is writable)."""
        self.export_formats: tuple[ExportFormat, ...] = (
            _fmt("points", "text/csv", _csv),
            _fmt("figure", "application/json", _fig),
            _fmt("broken", "text/csv", _bad),
        )

    def steps(self) -> list[StepSpec]:
        """Reuse the lctt wizard."""
        return register().steps()

    def recompute(self, points: tuple[CapturedPoint, ...]) -> Result[AnalysisResult, ComputeError]:
        """No values."""
        return Ok(AnalysisResult(values={}))


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    """App with the export lab registered, lifespan running."""
    labs = LabRegistry()
    assert labs.register(ExportLab()).is_ok
    with TestClient(create_app(AppSettings(data_root=tmp_path, labs=labs))) as c:
        yield c


def _open(c: TestClient) -> None:
    assert c.post("/api/sessions", json={"lab": "exp", "slug": "t"}).status_code == 201


# frob:tests python/sadi/server/routes/export.py::make_export_router
def test_no_session_is_problem_with_hint(client: TestClient) -> None:
    """Both endpoints refuse with a 409 problem+json and a hint when nothing is open."""
    for url in ("/api/export", "/api/export/points"):
        res = client.get(url)
        assert res.status_code == 409
        assert res.headers["content-type"].startswith("application/problem+json")
        assert res.json()["hint"]


# frob:tests python/sadi/server/routes/export.py::make_export_router
def test_list_formats(client: TestClient) -> None:
    """The lab's formats are listed with download flags."""
    _open(client)
    got = {f["id"]: f for f in client.get("/api/export").json()}
    assert set(got) == {"points", "figure", "broken"}
    assert got["points"]["download"] is True
    assert got["figure"]["download"] is False


# frob:tests python/sadi/server/routes/export.py::render_export
def test_csv_download_and_figure_json(client: TestClient) -> None:
    """CSV carries Content-Disposition; figure data is plain inline JSON."""
    _open(client)
    csv = client.get("/api/export/points")
    assert csv.status_code == 200
    assert csv.headers["content-type"].startswith("text/csv")
    assert "attachment" in csv.headers["content-disposition"]
    assert csv.headers["content-disposition"].endswith('-points.csv"')
    assert csv.text.startswith("session,points\n")
    fig = client.get("/api/export/figure")
    assert fig.status_code == 200
    assert "content-disposition" not in fig.headers
    assert fig.json() == {"x": [1, 2], "y": [3, 4]}


# frob:tests python/sadi/server/routes/export.py::render_export
def test_unknown_format_and_writer_failure(client: TestClient) -> None:
    """Unknown id is a 404 naming the choices; a failing writer is a problem with a hint."""
    _open(client)
    miss = client.get("/api/export/nope")
    assert miss.status_code == 404
    assert "points" in miss.json()["hint"]
    bad = client.get("/api/export/broken")
    assert bad.status_code >= 400
    assert bad.headers["content-type"].startswith("application/problem+json")
    assert bad.json()["hint"]


# frob:tests python/sadi/server/routes/export.py::render_export
def test_export_is_read_only(client: TestClient, tmp_path: Path) -> None:
    """Exporting leaves every file under the data root byte-identical and adds none."""
    _open(client)

    def snap() -> dict[str, bytes]:
        return {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}

    before = {k: v for k, v in snap().items() if not k.endswith(".lock")}
    client.get("/api/export/points")
    client.get("/api/export/figure")
    after = {k: v for k, v in snap().items() if not k.endswith(".lock")}
    assert after == before
