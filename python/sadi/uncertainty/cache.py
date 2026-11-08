"""Thread-safe keyed cache used to memoise traced and compiled expressions."""

# frob:ticket 01M6W7R1RD3P97HFFDZ2NVD83Y

from __future__ import annotations

import threading
from collections.abc import Callable, Hashable
from typing import Generic, TypeVar

from typani import Err, Ok, Result

from sadi.logging_setup import get_logger

_log = get_logger(__name__)

K = TypeVar("K", bound=Hashable)
V = TypeVar("V")
E = TypeVar("E")


class KeyedCache(Generic[K, V, E]):
    """Memoise successful `Result` computations by key; errors are never cached."""

    def __init__(self, name: str) -> None:
        """Create an empty cache labelled `name` for log lines."""
        self._name = name
        self._lock = threading.RLock()
        self._store: dict[K, V] = {}
        self.hits = 0
        self.misses = 0

    def get_or_compute(self, key: K, compute: Callable[[], Result[V, E]]) -> Result[V, E]:
        """Return the cached value for `key`, else run `compute` and store an Ok result."""
        with self._lock:
            if key in self._store:
                self.hits += 1
                _log.debug("%s cache hit", self._name)
                return Ok(self._store[key])
            self.misses += 1
        result = compute()
        if isinstance(result, Ok):
            with self._lock:
                self._store[key] = result.danger_ok
            _log.debug("%s cache store", self._name)
        elif isinstance(result, Err):
            _log.debug("%s compute failed; not cached", self._name)
        return result

    def clear(self) -> None:
        """Drop every entry and reset the hit/miss counters."""
        with self._lock:
            self._store.clear()
            self.hits = 0
            self.misses = 0
            _log.info("%s cache cleared", self._name)

    def __len__(self) -> int:
        """Return the number of cached entries."""
        with self._lock:
            return len(self._store)
