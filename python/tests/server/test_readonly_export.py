"""Read-only export of a closed session: no writer, version, WAL append or device; files untouched."""

# frob:ticket 01M724AKTJNNRY06637VBQ0A3E

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel
from typani import Ok, Result

from sadi.core.errors import ComputeError
from sadi.core.lab import AnalysisResult, ExportFormat, ExportFormatId, LabId, StepSpec
from sadi.core.models import CapturedPoint, RunState
from sadi.core.registry import LabRegistry
from sadi.labs.lctt.plugin import register
from sadi.server.app import AppSettings, create_app
from sadi.server.routes.export import stamp_recovered

WINDOW = {"first_raw_seq": 1, "last_raw_seq": 5}


def _csv(run: RunState, res: AnalysisResult) -> Result[bytes, ComputeError]:
    return Ok(f"session,points\n{run.session_id},{len(run.points)}\n".encode("ascii"))


class ExportLab:
    """The lctt steps with one trivial CSV export format."""

    id = LabId("exp")
    title = "Export lab"
    models: tuple[type[BaseModel], ...] = ()

    def __init__(self) -> None:
        """Declare the format per instance."""
        self.export_formats: tuple[ExportFormat, ...] = (
            ExportFormat(
                id=ExportFormatId("points"), title="points", media_type="text/csv", writer=_csv
            ),
        )

    def steps(self) -> list[StepSpec]:
        """Reuse the lctt wizard."""
        return register().steps()

    def recompute(self, points: tuple[CapturedPoint, ...]) -> Result[AnalysisResult, ComputeError]:
        """No values."""
        return Ok(AnalysisResult(values={}))


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    """App with no device and the export lab registered."""
    labs = LabRegistry()
    assert labs.register(ExportLab()).is_ok
    with TestClient(create_app(AppSettings(data_root=tmp_path, labs=labs))) as c:
        yield c


def _digest(root: Path) -> dict[str, str]:
    """Map every file under `root` (relative path) to its sha256."""
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def _closed(c: TestClient) -> str:
    """Create a session with one point, close it, return its name."""
    name = c.post("/api/sessions", json={"lab": "exp", "slug": "t"}).json()["name"]
    assert c.post("/api/session/wizard/skip", json={"step": "setup"}).status_code == 200
    body = {"phase": "calibration", "inputs": {"volts": 1.0, "height": 0.01}, "window": WINDOW}
    assert c.post("/api/session/points", json=body).status_code == 201
    assert c.post("/api/session/close").status_code == 204
    return name


# frob:tests python/sadi/server/routes/export.py::render_closed_export
# frob:tests python/sadi/server/routes/export.py::make_export_router
def test_closed_export_changes_nothing_on_disk(client: TestClient, tmp_path: Path) -> None:
    """Every file in the session dir (and the whole data root) hashes the same after the export."""
    name = _closed(client)
    sdir = tmp_path / "sessions" / name
    before_dir, before_root = _digest(sdir), _digest(tmp_path)
    listing = sorted(p.name for p in (tmp_path / "sessions").iterdir())
    res = client.get(f"/api/sessions/{name}/export/points")
    assert res.status_code == 200, res.text
    assert res.text == f"session,points\n{name},1\n"
    assert res.headers["content-disposition"].endswith('-points.csv"')
    assert "x-sadi-saved" not in res.headers
    for _ in range(2):
        assert client.get(f"/api/sessions/{name}/export/points").status_code == 200
    assert _digest(sdir) == before_dir
    assert _digest(tmp_path) == before_root
    assert sorted(p.name for p in (tmp_path / "sessions").iterdir()) == listing
    assert client.get("/api/session").status_code == 409  # still nothing open


# frob:tests python/sadi/server/service.py::SessionService.read_closed
def test_open_session_is_refused_with_hint(client: TestClient, tmp_path: Path) -> None:
    """The session being written cannot be exported this way; nothing changes."""
    name = client.post("/api/sessions", json={"lab": "exp", "slug": "t"}).json()["name"]
    before = _digest(tmp_path / "sessions" / name)
    res = client.get(f"/api/sessions/{name}/export/points")
    assert res.status_code == 409
    assert res.headers["content-type"].startswith("application/problem+json")
    assert res.json()["hint"]
    assert {k for k in _digest(tmp_path / "sessions" / name)} >= set(before)


# frob:tests python/sadi/server/service.py::SessionService.read_closed
def test_unknown_session_and_format(client: TestClient) -> None:
    """Unknown names and formats are 404 problems with hints; path tricks are refused."""
    name = _closed(client)
    for url in (
        "/api/sessions/nope/export/points",
        f"/api/sessions/{name}/export/nope",
    ):
        res = client.get(url)
        assert res.status_code == 404, url
        assert res.json()["hint"]


# frob:tests python/sadi/server/service.py::SessionService.read_closed
def test_corrupt_session_is_refused_and_untouched(client: TestClient, tmp_path: Path) -> None:
    """A damaged WAL gives a clear problem and the bytes on disk are left exactly as found."""
    name = _closed(client)
    sdir = tmp_path / "sessions" / name
    segs = sorted((sdir / "wal").iterdir())
    seg = segs[0]
    data = bytearray(seg.read_bytes())
    for i in range(64, 72):  # damage the first frame only; valid frames follow, so not a torn tail
        data[i] ^= 0xFF
    seg.write_bytes(bytes(data))
    before = _digest(sdir)
    res = client.get(f"/api/sessions/{name}/export/points")
    assert res.status_code >= 400
    assert res.headers["content-type"].startswith("application/problem+json")
    assert res.json()["hint"]
    assert _digest(sdir) == before


# frob:tests python/sadi/server/service.py::SessionService.read_closed
# frob:tests python/sadi/server/routes/export.py::make_export_router
def test_torn_tail_exports_verified_prefix_with_header(client: TestClient, tmp_path: Path) -> None:
    """A crash-style torn tail still downloads the verified prefix, flagged by a header, untouched."""
    name = _closed(client)
    sdir = tmp_path / "sessions" / name
    seg = sorted((sdir / "wal").iterdir())[-1]
    with seg.open("ab") as f:
        f.write(b"\x07\x00\x00")  # a partial frame, as left by power loss
    before = _digest(sdir)
    res = client.get(f"/api/sessions/{name}/export/points")
    assert res.status_code == 200, res.text
    lines = res.text.splitlines()
    assert lines[0].startswith("# RECOVERED:")
    assert "\n".join(lines[1:]) == f"session,points\n{name},1"
    assert res.headers["x-sadi-torn-tail"].count("/") == 1
    disp = res.headers["content-disposition"]
    assert 'filename="RECOVERED-' in disp
    assert "RECOVERED-RECOVERED-" not in disp
    assert _digest(sdir) == before


# frob:tests python/sadi/server/routes/export.py::stamp_recovered
def test_stamp_recovered_csv_and_json() -> None:
    """CSV gets a leading comment line; JSON gets a `recovered` key (wrapping non-objects)."""
    assert stamp_recovered(b"a,b\n", "text/csv", "0/5").startswith(b"# RECOVERED: ")
    assert b'"recovered"' in stamp_recovered(b'{"x": 1}', "application/json", "0/5")
    wrapped = stamp_recovered(b"[1]", "application/json", "0/5")
    assert b'"data": [1]' in wrapped
