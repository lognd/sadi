"""Skip the sadi_py tests cleanly when the compiled extension is not built."""

# frob:ticket 01M6Z3V40NSSQZY6D4BVFV301C
from __future__ import annotations

import importlib
import logging
from typing import Any

log = logging.getLogger(__name__)

_ABSENT = frozenset({"sadi_py", "sadi_py._native"})


def extension_missing() -> bool:
    """Return True only if sadi_py or its native module is absent; other errors propagate."""
    try:
        importlib.import_module("sadi_py")
    except ModuleNotFoundError as exc:
        if exc.name in _ABSENT:
            log.info("sadi_py extension not built (%s); skipping its tests", exc.name)
            return True
        raise
    return False


def pytest_ignore_collect(collection_path: Any, config: Any) -> bool | None:
    """Ignore *.py test files under this crate when the extension is unbuilt."""
    del config
    if collection_path.suffix == ".py" and collection_path.name != "conftest.py":
        return True if extension_missing() else None
    return None
