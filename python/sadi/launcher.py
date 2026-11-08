"""`sadi` launcher: doctor preflight, then uvicorn serving the API and built web assets."""

# frob:ticket 01M6WMGMM1BP37GS27VRRX9AYP
from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from typani import Err, Ok, Result

from sadi.doctor import exit_code, run
from sadi.doctor.cli import main as doctor_main
from sadi.doctor.render_text import render
from sadi.doctor.schema import DoctorReport, RunOptions
from sadi.logging_setup import get_logger
from sadi.server.app import AppSettings, RootLockStartupError, create_app

_log = get_logger(__name__)

EXIT_USAGE = 64
EXIT_PREFLIGHT = 2
EXIT_LOCK = 3
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DEFAULT_WEB_DIST = Path("web") / "dist"

Serve = Callable[[FastAPI, str, int], None]


def _out(text: str) -> None:
    """Write to stdout."""
    sys.stdout.write(text)


def _err(text: str) -> None:
    """Write to stderr."""
    sys.stderr.write(text)


def mount_web(app: FastAPI, dist: Path) -> bool:
    """Mount the built web assets at `/` when `dist/index.html` exists; return whether mounted."""
    if not (dist / "index.html").is_file():
        _log.warning("no built web assets at %s; serving the API only", dist)
        return False
    app.mount("/", StaticFiles(directory=dist, html=True), name="web")
    _log.info("serving web assets from %s", dist)
    return True


def preflight(data_root: Path, port: int) -> Result[DoctorReport, str]:
    """Run the doctor read-only; Err carries the rendered report when a blocker is found."""
    opts = RunOptions(data_root=str(data_root), api_port=port)
    got = run(opts)
    if got.is_err:
        _log.error("doctor could not run: %s", got.danger_err.value)
        return Err(f"doctor could not run: {got.danger_err.value}\n")
    report = got.danger_ok
    if exit_code(report) >= EXIT_PREFLIGHT:
        _log.error("doctor preflight blocked startup")
        return Err(render(report))
    if exit_code(report) != 0:
        _log.warning("doctor preflight reported problems; starting anyway")
    return Ok(report)


def _uvicorn_serve(app: FastAPI, host: str, port: int) -> None:
    """Run uvicorn on `app` (blocking)."""
    uvicorn.run(app, host=host, port=port, log_level="info")


def _parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    p = argparse.ArgumentParser(prog="sadi", description="Run SADI locally.")
    sub = p.add_subparsers(dest="command")
    serve = sub.add_parser("serve", help="preflight, then start the server (default)")
    serve.add_argument("--host", default=DEFAULT_HOST)
    serve.add_argument("--port", type=int, default=DEFAULT_PORT)
    serve.add_argument("--data-root", type=Path, default=Path("data"))
    serve.add_argument("--web-dist", type=Path, default=DEFAULT_WEB_DIST)
    serve.add_argument("--skip-preflight", action="store_true", help="do not run the doctor")
    sub.add_parser("doctor", help="run sadi-doctor; remaining arguments are passed through")
    return p


def _serve(args: argparse.Namespace, serve: Serve) -> int:
    """Preflight, build the app, mount the web and serve; return the exit code."""
    if not args.skip_preflight:
        pre = preflight(args.data_root, args.port)
        if pre.is_err:
            _err(pre.danger_err)
            _err("sadi: doctor preflight failed; follow the steps above, then retry.\n")
            return EXIT_PREFLIGHT
    app = create_app(AppSettings(data_root=args.data_root))
    mount_web(app, args.web_dist)
    _log.info("starting server on %s:%d", args.host, args.port)
    try:
        serve(app, args.host, args.port)
    except RootLockStartupError as exc:
        _log.error("data-root lock refused: %s", exc)
        _err(f"sadi: {exc}\n")
        return EXIT_LOCK
    return 0


def main(argv: Sequence[str] | None = None, serve: Serve = _uvicorn_serve) -> int:
    """Entry point; `serve` is injectable for tests. Returns the process exit code."""
    args_in = list(sys.argv[1:] if argv is None else argv)
    if args_in[:1] == ["doctor"]:
        return doctor_main(args_in[1:])
    if not args_in or (args_in[0].startswith("-") and args_in[0] not in ("-h", "--help")):
        args_in = ["serve", *args_in]
    try:
        args = _parser().parse_args(args_in)
    except SystemExit as e:
        return 0 if e.code in (None, 0) else EXIT_USAGE
    logging.getLogger("sadi").setLevel(logging.INFO)
    return _serve(args, serve)


if __name__ == "__main__":
    raise SystemExit(main())
