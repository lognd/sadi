"""Where the built web UI lives in a source checkout, independent of the working directory."""

from __future__ import annotations

from pathlib import Path

# python/sadi/webdist.py -> parents[2] is the repository root.
CHECKOUT_WEB_DIST = Path(__file__).resolve().parents[2] / "web" / "dist"

BUILD_UI_HINT = "run: cd python && uv run python ../packaging/build_ui.py"
