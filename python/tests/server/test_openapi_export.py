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
