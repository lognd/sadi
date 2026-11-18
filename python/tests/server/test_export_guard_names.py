"""Cross-site export GET refusal (creates:python/tests/server/test_export_guard_names.py)."""

# frob:ticket 01M72D3CTDED2MGDY721RSM8M4

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sadi.plugins import PluginRegistry
from sadi.plugins.builtin import builtin_source
from sadi.server.app import AppSettings, create_app


def _client() -> TestClient:
    reg = PluginRegistry.discover([builtin_source()])
    return TestClient(create_app(AppSettings(registry=reg, data_root=Path("x"))))


@pytest.mark.parametrize("path", ["/api/export/lctt-csv", "/api/export/formats"])
# frob:tests python/sadi/server/security.py::OriginGuard._verdict
def test_cross_site_get_refused(path: str) -> None:
    """A cross-site page cannot trigger an export GET (it writes a saved copy)."""
    res = _client().get(path, headers={"Sec-Fetch-Site": "cross-site"})
    assert res.status_code == 403


@pytest.mark.parametrize("site", ["same-origin", "same-site", "none"])
# frob:tests python/sadi/server/security.py::OriginGuard._verdict
def test_non_cross_site_get_passes_guard(site: str) -> None:
    """Same-origin, same-site, and user-initiated GETs are not refused by the guard."""
    res = _client().get("/api/export/lctt-csv", headers={"Sec-Fetch-Site": site})
    assert res.status_code != 403


# frob:tests python/sadi/server/security.py::OriginGuard._verdict
def test_absent_header_get_passes_guard() -> None:
    """Non-browser clients send no Sec-Fetch-Site and stay allowed."""
    assert _client().get("/api/export/lctt-csv").status_code != 403
