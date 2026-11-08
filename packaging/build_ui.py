"""Build the web UI (npm ci, npm run build) and copy web/dist into python/sadi/_ui/."""

# frob:ticket 01M6W7RAW944RFCMESYZKJSYXC
from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from typani import Err, Ok, Result, propagate

_log = logging.getLogger("sadi.packaging.build_ui")

ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "web"
UI_DIR = ROOT / "python" / "sadi" / "_ui"
KEEP = ".gitkeep"

#: Runs an argv in a cwd; Ok(None) on success, Err(message) otherwise.
Runner = Callable[[Sequence[str], Path], Result[None, str]]


def run_command(argv: Sequence[str], cwd: Path) -> Result[None, str]:
    """Run `argv` in `cwd` (no shell, cross-platform exe lookup); Err on failure."""
    exe = shutil.which(argv[0])
    if exe is None:
        _log.error("%s not found on PATH", argv[0])
        return Err(f"{argv[0]} not found on PATH")
    cmd = [exe, *argv[1:]]
    _log.info("running %s in %s", cmd, cwd)
    try:
        proc = subprocess.run(cmd, cwd=cwd, check=False)
    except OSError as exc:
        _log.error("could not run %s: %s", cmd, exc)
        return Err(f"could not run {argv[0]}: {exc}")
    if proc.returncode != 0:
        _log.error("%s exited with %d", cmd, proc.returncode)
        return Err(f"{' '.join(argv)} exited with {proc.returncode}")
    return Ok(None)


def clear_ui(ui_dir: Path) -> Result[None, str]:
    """Remove everything in `ui_dir` except `.gitkeep`, creating it if absent."""
    try:
        ui_dir.mkdir(parents=True, exist_ok=True)
        for child in ui_dir.iterdir():
            if child.name == KEEP:
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    except OSError as exc:
        _log.error("could not clear %s: %s", ui_dir, exc)
        return Err(f"could not clear {ui_dir}: {exc}")
    _log.info("cleared %s", ui_dir)
    return Ok(None)


@propagate
def copy_dist(dist: Path, ui_dir: Path) -> Result[Path, str]:
    """Replace the contents of `ui_dir` with `dist`; Ok carries `ui_dir`."""
    if not (dist / "index.html").is_file():
        _log.error("no index.html in %s", dist)
        return Err(f"build output {dist} has no index.html")
    clear_ui(ui_dir).unwrap()
    try:
        shutil.copytree(dist, ui_dir, dirs_exist_ok=True)
    except OSError as exc:
        _log.error("copy %s -> %s failed: %s", dist, ui_dir, exc)
        return Err(f"could not copy {dist} to {ui_dir}: {exc}")
    _log.info("copied %s -> %s", dist, ui_dir)
    return Ok(ui_dir)


@propagate
def build_ui(
    web_dir: Path = WEB_DIR,
    ui_dir: Path = UI_DIR,
    runner: Runner = run_command,
    *,
    install: bool = True,
) -> Result[Path, str]:
    """Run `npm ci` (if `install`) and `npm run build` in `web_dir`, then copy dist to `ui_dir`."""
    if not (web_dir / "package.json").is_file():
        _log.error("no package.json in %s", web_dir)
        return Err(f"{web_dir} is not a web project (package.json missing)")
    steps: list[list[str]] = [["npm", "ci"]] if install else []
    steps.append(["npm", "run", "build"])
    for step in steps:
        runner(step, web_dir).unwrap()
    return copy_dist(web_dir / "dist", ui_dir)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry: `python packaging/build_ui.py [--no-install]`; return the exit code."""
    args = list(sys.argv[1:] if argv is None else argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    got = build_ui(install="--no-install" not in args)
    if got.is_err:
        _log.error("UI build failed: %s", got.danger_err)
        return 1
    _log.info("UI bundled into %s", got.danger_ok)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
