"""Fail if sadi.uncertainty shadows a typani public export (CI lint step)."""

# frob:ticket 01M6W7R1T397W3C0JZV66MX8BW

from __future__ import annotations

import importlib
import logging
import re
import sys
from pathlib import Path

import typani
from typani import Err, ErrorSet, Ok, Result

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
PYTHON_DIR = REPO_ROOT / "python"
TARGET_MODULE = "sadi.uncertainty"

# Matches `import x as propagate` / `from m import x as catching` for any typani name.
_ALIAS_TEMPLATE = r"^\s*(?:from\s+\S+\s+)?import\b[^\n#]*\bas\s+({names})\b"


class CheckError(ErrorSet):
    """Failures of the checker itself (not collisions)."""

    ImportFailed = "Could not import the module under check"
    NoAll = "Module under check does not define __all__"


def typani_exports() -> list[str]:
    """Return typani's public export names (its __all__, minus dunders)."""
    names = [n for n in typani.__all__ if not n.startswith("__")]
    log.debug("typani exports %d public names", len(names))
    return names


def export_collisions(module_name: str = TARGET_MODULE) -> Result[list[str], CheckError]:
    """List names in module_name.__all__ that are also typani public exports."""
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        log.error("cannot import %s: %s", module_name, exc)
        return Err(CheckError.ImportFailed).note(f"{module_name}: {exc}")
    exported = getattr(module, "__all__", None)
    if exported is None:
        log.error("%s has no __all__", module_name)
        return Err(CheckError.NoAll)
    hits = sorted(set(exported) & set(typani_exports()))
    if hits:
        log.warning("%s.__all__ collides with typani: %s", module_name, hits)
    else:
        log.info("%s.__all__ has no typani collisions", module_name)
    return Ok(hits)


def alias_collisions(root: Path = PYTHON_DIR) -> list[str]:
    """Grep python sources for `import ... as <typani name>` aliasing."""
    pattern = re.compile(
        _ALIAS_TEMPLATE.format(names="|".join(map(re.escape, typani_exports()))), re.M
    )
    hits: list[str] = []
    for path in sorted(root.rglob("*.py")):
        if ".venv" in path.parts:
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line):
                hits.append(f"{path}:{lineno}: {line.strip()}")
    log.info("alias scan of %s found %d hits", root, len(hits))
    return hits


def main() -> int:
    """CLI entry: print problems to stdout and return a process exit code."""
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    problems: list[str] = []
    match export_collisions():
        case Ok(hits):
            problems += [f"{TARGET_MODULE}.__all__ shadows typani export: {h}" for h in hits]
        case Err(error):
            problems.append(f"check failed: {error}")
    problems += [f"typani name aliased: {h}" for h in alias_collisions()]
    for p in problems:
        sys.stdout.write(p + "\n")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
