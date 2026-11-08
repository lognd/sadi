"""Public export seam for lab modules: re-exports the store's atomic CSV/export primitives.

Labs may not import `sadi.store`; this module is the single allowed door. It adds no logic,
so atomicity (tmp + fsync + no-replace rename) and provenance sidecars stay owned by the store.
"""

# frob:ticket 01M6WMGMGPZ58NGQ5J5XVRN5TD
from __future__ import annotations

from sadi.store.csv_export import UTF8_BOM, render_csv
from sadi.store.exports import ExportResult, write_export
from sadi.store.exports import _HasPath as HasPath  # noqa: PLC2701 - public alias of the protocol

__all__ = ["UTF8_BOM", "ExportResult", "HasPath", "render_csv", "write_export"]
