"""Shared bound on how many items a combination may use, so big inventories stay plannable."""

from __future__ import annotations

import math

from sadi.logging_setup import get_logger

__all__ = ["COMBO_BUDGET", "MAX_INVENTORY", "max_combo_size"]

_log = get_logger(__name__)

#: Most weights (or heights) one inventory may hold; the page stops adding rows here.
MAX_INVENTORY = 120
#: Most candidate combinations enumerated; larger inventories use smaller combinations.
COMBO_BUDGET = 20000


def max_combo_size(n: int, limit: int | None = None) -> int:
    """Largest k such that all combinations of up to k of n items fit the budget (and <= limit)."""
    total = 0
    k = 0
    cap = n if limit is None else min(n, limit)
    while k < cap:
        total += math.comb(n, k + 1)
        if total > COMBO_BUDGET and k >= 1:
            break
        k += 1
    _log.debug("combo size for %d items: up to %d at a time", n, k)
    return k
