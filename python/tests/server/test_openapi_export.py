"""Drift test: the committed web/src/api/openapi.json must match the live app."""

# frob:ticket 01M6WTCA5YQJPPTGFH316XQ2DQ

from __future__ import annotations

import json
from pathlib import Path

from sadi.server.openapi_export import SPEC_RELPATH, main, render_openapi

_REPO = Path(__file__).resolve().parents[3]


# frob:tests python/sadi/server/openapi_export.py::render_openapi
def test_render_is_deterministic() -> None:
    """Two renders are byte-identical and ASCII-only."""
    a = render_openapi()
    assert a == render_openapi()
    assert a.isascii()
    assert "/api/plugins" in json.loads(a)["paths"]


def test_committed_spec_not_stale() -> None:
    """Fails when routes changed without re-running `npm run gen:api` in web/."""
    committed = (_REPO / SPEC_RELPATH).read_text(encoding="utf-8")
    assert committed == render_openapi(), "regenerate: cd web && npm run gen:api"


# frob:tests python/sadi/server/openapi_export.py::write_openapi
# frob:tests python/sadi/server/openapi_export.py::main
def test_main_writes_file(tmp_path: Path) -> None:
    """main() with a path argument writes the rendered spec there."""
    dest = tmp_path / "o.json"
    assert main([str(dest)]) == 0
    assert dest.read_text(encoding="utf-8") == render_openapi()


# frob:ticket 01M72VV7AGMWE3JE4MZFA8P5T6
# frob:tests python/sadi/server/routes/sessions.py::make_sessions_router
def test_capture_declares_409_503_and_reason_enum() -> None:
    """The capture route documents its problem responses; reasons are an enum."""
    spec = json.loads(render_openapi())
    post = spec["paths"]["/api/session/points"]["post"]
    assert {"201", "409", "503"} <= set(post["responses"])
    reasons = spec["components"]["schemas"]["ConfidenceIndicator"]["properties"]["reasons"]
    assert "enum" in json.dumps(reasons) or "$ref" in json.dumps(reasons)
    assert "no_calibration" in json.dumps(spec["components"]["schemas"])
