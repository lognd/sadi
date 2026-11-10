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
    """Exporting never changes an existing file; downloads only add files under exports/."""
    _open(client)

    def snap() -> dict[str, bytes]:
        return {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}

    before = {k: v for k, v in snap().items() if not k.endswith(".lock")}
    client.get("/api/export/figure")
    assert {k: v for k, v in snap().items() if not k.endswith(".lock")} == before
    client.get("/api/export/points")
    after = {k: v for k, v in snap().items() if not k.endswith(".lock")}
    assert all(after[k] == v for k, v in before.items())
    assert all("/exports/points/" in k for k in after.keys() - before.keys())


# frob:tests python/sadi/server/routes/export.py::render_export
def test_real_lctt_lab_lists_csv_and_refuses_empty_session(tmp_path: Path) -> None:
    """The real lctt lab lists lctt-csv; an empty session cannot render it (problem, no file)."""
    labs = LabRegistry()
    assert labs.register(register()).is_ok
    with TestClient(create_app(AppSettings(data_root=tmp_path, labs=labs))) as c:
        assert c.post("/api/sessions", json={"lab": "lctt", "slug": "t"}).status_code == 201
        listed = {f["id"]: f for f in c.get("/api/export").json()}
        assert listed["lctt-csv"]["download"] is True
        assert listed["lctt-csv"]["media_type"] == "text/csv"
        res = c.get("/api/export/lctt-csv")
        assert res.status_code >= 400
        assert res.headers["content-type"].startswith("application/problem+json")


# frob:tests python/sadi/server/routes/export.py::_save_copy
def test_download_is_also_kept_in_session_folder(client: TestClient, tmp_path: Path) -> None:
    """Audit1 #22: a download is written atomically under exports/ with a sidecar; never overwritten."""
    _open(client)
    first = client.get("/api/export/points")
    second = client.get("/api/export/points")
    assert first.headers["x-sadi-saved"].startswith("exports/points/0001-")
    assert second.headers["x-sadi-saved"].startswith("exports/points/0002-")
    (sess,) = (tmp_path / "sessions").iterdir()
    kept = sorted(p for p in (sess / "exports" / "points").iterdir() if not p.name.startswith("."))
    assert len([p for p in kept if p.suffix == ".csv"]) == 2
    assert len([p for p in kept if p.name.endswith(".prov.json")]) == 2
    assert kept[0].read_bytes() == first.content
    assert not list((sess / "exports" / "points").glob(".*.tmp-*"))
    assert sess.name.split(".v")[0].endswith("-t")


# frob:tests python/sadi/server/routes/export.py::make_export_router
def test_figure_upload_is_kept_without_overwrite(client: TestClient, tmp_path: Path) -> None:
    """Audit1 #22: a browser-rendered PNG is stored in exports/figure with the session name."""
    _open(client)
    png = b"\x89PNG\r\n\x1a\n" + b"x" * 32
    a = client.post("/api/export/figure/points", content=png)
    b = client.post("/api/export/figure/points", content=png)
    assert a.status_code == 200 and a.json()["saved"] != b.json()["saved"]
    assert a.json()["saved"].endswith("-points.png") and "-t.v001" in a.json()["saved"]
    assert client.post("/api/export/figure/points", content=b"").status_code == 400
