"""Boundary test: acquisition and pipeline never import sadi_py/serial."""

# frob:ticket 01M6Z4H8WCX7C9V94Y7ESJP9HA

from __future__ import annotations

import ast
from pathlib import Path
from types import ModuleType

import sadi.api.acquisition as acq
import sadi.core.pipeline as pl
from sadi.core.errors import DeviceCode

_BANNED = {"sadi_py", "serial"}


def _imported_roots(mod: ModuleType) -> set[str]:
    """Top-level module names imported anywhere in `mod`'s source."""
    tree = ast.parse(Path(mod.__file__ or "").read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


# frob:tests python/sadi/core/pipeline.py::BlockLike
# frob:tests python/sadi/api/acquisition.py::BlockSource
def test_modules_do_not_import_sadi_py_or_serial() -> None:
    """Neither module may import the raw device layer."""
    for mod in (acq, pl):
        assert not (_imported_roots(mod) & _BANNED), mod.__name__


def test_stop_device_failure_is_mapped_not_raised(tmp_path: Path) -> None:
    """A raising stop_device is absorbed via the facade and maps to a DeviceCode."""
    from sadi.core.devfacade import close_quietly

    def boom() -> None:
        raise OSError("device gone")

    res = close_quietly("t", boom)
    assert res.is_err
    assert isinstance(res.danger_err.code, DeviceCode)
    assert res.danger_err.code is DeviceCode.DISCONNECTED
