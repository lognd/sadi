"""`sadi` launcher: doctor preflight, then uvicorn serving the API and built web assets."""

# frob:ticket 01M6X572N6WB1053QZ1WV4W4WY
# frob:ticket 01M6WMGMM1BP37GS27VRRX9AYP
# frob:ticket 01M6W7RAW944RFCMESYZKJSYXC
# frob:ticket 01M6WTZVX9DFPHBKVJ1NXB07G0
# frob:ticket 01M6X06TPZ3W86FDHQPX01MME8
# frob:ticket 01M6Z52N7A69ET20H5GMS8S7BG
# frob:ticket 01M71Z6EMJ9QP7716699S5SC5X
from __future__ import annotations

import argparse
import ipaddress
import logging
import os
import socket
import sys
import threading
import time
import webbrowser
from collections.abc import Callable, Mapping, Sequence
from importlib import metadata, resources
from pathlib import Path
from typing import TYPE_CHECKING, Final, cast

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from typani import Err, Ok, Result

from sadi.core import devfacade
from sadi.doctor import exit_code, run
from sadi.doctor.cli import main as doctor_main
from sadi.doctor.render_text import render
from sadi.doctor.schema import DoctorReport, RunOptions
from sadi.logging_setup import get_logger
from sadi.webdist import BUILD_UI_HINT, CHECKOUT_WEB_DIST

# Heavy modules (sadi.store via core/server/plugins) are imported lazily inside functions:
# a spawn-context worker re-imports the entry script, and WRK-010 requires that child to
# stay free of sadi.store.
if TYPE_CHECKING:
    from sadi.bench.ad3.launch import Ad3Guard
    from sadi.core.device import DeviceService  # frob:ticket 01M6Z4AH5A8BTYYG8G7FEV63Y8
    from sadi.core.registry import LabRegistry
    from sadi.plugins.registry import PluginRegistry

_log = get_logger(__name__)

EXIT_USAGE = 64
EXIT_PREFLIGHT = 2
EXIT_LOCK = 3
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DEFAULT_WEB_DIST = CHECKOUT_WEB_DIST
EXIT_SELFTEST = 4
EXIT_PORT = 5
EXIT_DEVICE = 6
EXIT_AD3 = 7
SIM_ENV = "SADI_SIM"
APP_NAME = "sadi"
BROWSER_WAIT_S = 15.0

Serve = Callable[[FastAPI, str, int], None]


def _out(text: str) -> None:
    """Write to stdout."""
    sys.stdout.write(text)


def _err(text: str) -> None:
    """Write to stderr."""
    sys.stderr.write(text)


def default_data_dir() -> Path:
    """Per-OS default data directory (platformdirs when installed, else XDG/APPDATA/macOS)."""
    try:
        from platformdirs import user_data_dir
    except ImportError:
        _log.info("platformdirs not installed; using built-in per-OS fallback")
        home = Path.home()
        if sys.platform == "win32":
            base = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        elif sys.platform == "darwin":
            base = home / "Library" / "Application Support"
        else:
            base = Path(os.environ.get("XDG_DATA_HOME", home / ".local" / "share"))
        return base / APP_NAME
    return Path(user_data_dir(APP_NAME, appauthor=False))


def is_loopback(host: str) -> bool:
    """Return whether `host` is `localhost` or a loopback IP literal."""
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _port_free(host: str, port: int) -> bool:
    """Return whether `host:port` can be bound right now (port 0 always can)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if sys.platform != "win32":
            # Match uvicorn: a port in TIME_WAIT after a crash is bindable, not busy. Skipped on
            # Windows, where SO_REUSEADDR would also let us "bind" a port a live server holds.
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port))
        except OSError:
            return False
    return True


def data_root_unwritable_hint(root: Path) -> str | None:
    """Return a plain-language hint when `root` (or its nearest existing parent) is not writable.

    Read-only check: nothing is created. None means the folder looks usable.
    """
    probe = root
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    if not probe.is_dir():
        return f"{probe} is not a folder, so SADI cannot keep your data in {root}."
    if os.access(probe, os.W_OK | os.X_OK):
        return None
    _log.error("data root %s is not writable (checked %s)", root, probe)
    return (
        f"Permission denied: SADI cannot write to {probe}. Pick a folder you own with "
        f"`--data-root <folder>`, or fix the folder's permissions, then start again."
    )


def pick_port(host: str, preferred: int, *, strict: bool) -> Result[int, str]:
    """Return `preferred` if free; else (unless `strict`) an ephemeral free port."""
    if _port_free(host, preferred):
        return Ok(preferred)
    if strict:
        _log.error("requested port %d is busy", preferred)
        return Err(f"port {preferred} is already in use")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, 0))
        except OSError as exc:
            _log.error("no free ephemeral port on %s: %s", host, exc)
            return Err(f"no free port available: {exc}")
        port = int(s.getsockname()[1])
    _log.warning("port %d busy; falling back to %d", preferred, port)
    return Ok(port)


def open_browser(url: str) -> Result[None, str]:
    """Open `url` in the default browser; Err (never raises) when that is impossible."""
    try:
        opened = webbrowser.open(url)
    except (webbrowser.Error, OSError) as exc:
        _log.warning("could not open browser: %s", exc)
        return Err(str(exc))
    if not opened:
        _log.warning("no browser available for %s", url)
        return Err("no browser available")
    return Ok(None)


def _browser_when_up(host: str, port: int, url: str) -> None:
    """Wait until the server accepts connections, then open the browser (thread body)."""
    deadline = time.monotonic() + BROWSER_WAIT_S
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                break
        except OSError:
            time.sleep(0.2)
    else:
        _log.warning("server did not come up; not opening browser")
        return
    if open_browser(url).is_err:
        _log.info("browser not opened; open %s manually", url)


def schedule_browser(host: str, port: int) -> threading.Thread:
    """Start a daemon thread that opens the UI once the server is listening."""
    url = f"http://{host}:{port}/"
    t = threading.Thread(target=_browser_when_up, args=(host, port, url), daemon=True)
    t.start()
    return t


def selftest() -> Result[int, str]:
    """Run a short simulator acquisition; Ok carries the packet count."""
    from sadi.doctor.devprobe import probe_sim

    facts = probe_sim()
    if not facts.binding_ok:
        return Err(f"simulator unavailable: {facts.detail}")
    if facts.timed_out or not facts.connect_ok or not facts.data_ok or facts.failed_scenarios:
        return Err(f"simulator acquisition failed: {facts.detail or facts.failed_scenarios}")
    return Ok(facts.packets)


def sim_requested(flag: bool, env: Mapping[str, str] | None = None) -> bool:
    """Return whether the simulator is wanted: the `--sim` flag or `SADI_SIM` set to 1/true/yes."""
    values = os.environ if env is None else env
    return flag or values.get(SIM_ENV, "").strip().lower() in ("1", "true", "yes")


def open_sim_device() -> Result[DeviceService, str]:
    """Open a simulator `DeviceService` for the app; Err when `sadi_py` or the open fails."""
    bound = devfacade.binding()
    if bound.is_err:
        detail = bound.danger_err.detail
        _log.error("simulator unavailable: %s", detail)
        return Err(f"simulator unavailable (sadi_py not importable): {detail}")
    from sadi.core.device import DeviceService, DeviceSource

    svc = DeviceService(DeviceSource(kind="sim", manual_load=True))
    opened = svc.open()
    if opened.is_err:
        _log.error("simulator open failed: %s", opened.danger_err.detail)
        return Err(f"simulator open failed: {opened.danger_err.detail}")
    _log.info("simulator device open")
    return Ok(svc)


def package_version() -> str:
    """Installed `sadi` version, or `unknown` when not installed."""
    try:
        return metadata.version("sadi")
    except metadata.PackageNotFoundError:
        return "unknown"


def resolve_web_dist(explicit: Path | None = None) -> Path:
    """Pick the UI dir: explicit path, else packaged `sadi/_ui`, else the checkout's `web/dist`."""
    if explicit is not None:
        _log.info("using explicit web dist %s", explicit)
        return explicit
    packaged = Path(str(resources.files("sadi") / "_ui"))
    if (packaged / "index.html").is_file():
        _log.info("using packaged UI at %s", packaged)
        return packaged
    _log.info("no packaged UI; falling back to %s", DEFAULT_WEB_DIST)
    return DEFAULT_WEB_DIST


def mount_web(app: FastAPI, dist: Path) -> bool:
    """Mount the built web assets at `/` when `dist/index.html` exists; return whether mounted."""
    if not (dist / "index.html").is_file():
        _log.warning("no built web assets at %s; serving the API only (%s)", dist, BUILD_UI_HINT)
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


def load_builtin_plugins() -> tuple[PluginRegistry, LabRegistry]:
    """Discover the built-in plugins and build the lab registry; failures are logged and warned.

    Never raises: a plugin that fails to load stays visible in the plugin registry (and
    `/api/plugins`) as failed, and is reported on stderr, but the app still starts.
    """
    from sadi.core.registry import LabRegistry
    from sadi.plugins.builtin import builtin_source
    from sadi.plugins.registry import PluginRegistry, PluginState

    plugins = PluginRegistry.discover([builtin_source()])
    for rec in plugins.records():
        if rec.state is PluginState.ENABLED:
            _log.info("built-in plugin %s enabled (%d labs)", rec.id, len(rec.labs))
            continue
        notes = "; ".join(f"{i.kind}: {i.note}" for i in rec.errors) or rec.state.value
        _log.error("built-in plugin %s is %s: %s", rec.id, rec.state.value, notes)
        _err(f"sadi: warning: plugin {rec.id} is {rec.state.value}: {notes}\n")
    for issue in plugins.source_errors():
        _log.error("plugin source failed: %s", issue.note)
        _err(f"sadi: warning: plugin source failed: {issue.note}\n")
    labs = LabRegistry()
    for err in labs.add_plugins(plugins):
        _log.error("lab registration failed: %s", err)
    if not labs.ids():
        _log.error("no labs registered; sessions cannot be created")
        _err("sadi: warning: no labs available; sessions cannot be created\n")
    return plugins, labs


def _uvicorn_serve(app: FastAPI, host: str, port: int) -> None:
    """Run uvicorn on `app` (blocking)."""
    uvicorn.run(app, host=host, port=port, log_level="info")


def _parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    p = argparse.ArgumentParser(prog="sadi", description="Run SADI locally.")
    sub = p.add_subparsers(dest="command")
    serve = sub.add_parser("serve", help="preflight, then start the server (default)")
    serve.add_argument("--host", default=DEFAULT_HOST, help="loopback only unless overridden")
    serve.add_argument(
        "--allow-non-loopback", action="store_true", help="UNSAFE: permit a non-loopback --host"
    )
    serve.add_argument("--port", type=int, default=None, help=f"default {DEFAULT_PORT}, else free")
    serve.add_argument(
        "--data-root",
        "--data-dir",
        dest="data_root",
        type=Path,
        default=None,
        help="data directory (default: per-OS user data dir)",
    )
    serve.add_argument(
        "--recover-stale",
        action="store_true",
        help="take over a data folder left locked by a crashed sadi (never deletes data)",
    )
    serve.add_argument("--no-browser", action="store_true", help="do not open the browser")
    serve.add_argument("--sim", action="store_true", help="prefer the built-in simulator")
    serve.add_argument(
        "--device-port",
        default=None,
        help="serial port of the SADI board (default: SADI_PORT, else /dev/ttyUSB0)",
    )
    serve.add_argument("--ad3", action="store_true", help="open the Digilent AD3 (closed on exit)")
    serve.add_argument(
        "--synthetic-specimen",
        action="store_true",
        help="serve a SIMULATED copper wire instead of a device (needs the confirmation phrase)",
    )
    serve.add_argument(
        "--i-understand-this-is-fake",
        metavar="PHRASE",
        default=None,
        help="the typed confirmation phrase required by --synthetic-specimen",
    )
    serve.add_argument("--selftest", action="store_true", help="run a simulator acquisition, exit")
    serve.add_argument("--version", action="store_true", help="print the version and exit")
    serve.add_argument(
        "--web-dist", type=Path, default=None, help="UI dir (default: packaged, else web/dist)"
    )
    serve.add_argument("--skip-preflight", action="store_true", help="do not run the doctor")
    sub.add_parser("doctor", help="run sadi-doctor; remaining arguments are passed through")
    return p


SYNTHETIC_BANNER = (
    "\n"
    "########################################################################\n"
    "#  SYNTHETIC SPECIMEN: ALL DATA IS SIMULATED. NOT A REAL MEASUREMENT.  #\n"
    "#  Sessions and exports are labelled SYNTHETIC and cannot be mixed     #\n"
    "#  with real data. Do not submit this data as lab results.             #\n"
    "########################################################################\n"
    "\n"
)  # frob:ticket 01M71SYG3H3X7GJT21TE6MY8YC


def _resolve_synthetic(args: argparse.Namespace) -> Result[bool, str]:
    """Gate the synthetic source on the flag AND the typed phrase (never env; tty may prompt)."""
    from sadi.synthetic.confirm import check_enable

    phrase = args.i_understand_this_is_fake
    if args.synthetic_specimen and phrase is None and sys.stdin.isatty():
        from sadi.synthetic.provenance import CONFIRM_PHRASE

        _out(f'sadi: type exactly "{CONFIRM_PHRASE}" to use SIMULATED data: ')
        phrase = sys.stdin.readline().rstrip("\n")
    got = check_enable(args.synthetic_specimen, phrase)
    if got.is_err:
        return Err(str(got.danger_err))
    return Ok(got.danger_ok)


def _open_synthetic() -> DeviceService:
    """Open the seeded synthetic copper-wire source in place of a device."""
    from sadi.synthetic.device import SyntheticDevice

    dev = SyntheticDevice(seed=0)
    dev.open()
    return cast("DeviceService", dev)  # duck-typed stand-in (same surface)


def _serve(args: argparse.Namespace, serve: Serve) -> int:
    """Preflight, build the app, mount the web and serve; return the exit code."""
    if args.version:
        _out(f"sadi {package_version()}\n")
        return 0
    if args.selftest:
        got = selftest()
        if got.is_err:
            _err(f"sadi: selftest FAILED: {got.danger_err}\n")
            return EXIT_SELFTEST
        _out(f"sadi: selftest ok ({got.danger_ok} simulator packets)\n")
        return 0
    if not is_loopback(args.host) and not args.allow_non_loopback:
        _log.error("refusing non-loopback host %s", args.host)
        _err(
            f"sadi: refusing to bind {args.host}; only loopback is allowed "
            "(pass --allow-non-loopback to override, UNSAFE)\n"
        )
        return EXIT_USAGE
    port_got = pick_port(args.host, args.port or DEFAULT_PORT, strict=args.port is not None)
    if port_got.is_err:
        _err(f"sadi: {port_got.danger_err}\n")
        return EXIT_PORT
    port = port_got.danger_ok
    data_root = args.data_root if args.data_root is not None else default_data_dir()
    _out(f"sadi: data directory: {data_root}\n")
    unwritable = data_root_unwritable_hint(data_root)
    if unwritable is not None:
        _err(f"sadi: {unwritable}\n")
        return EXIT_LOCK
    synth = _resolve_synthetic(args)
    if synth.is_err:
        _err(f"sadi: {synth.danger_err}\n")
        return EXIT_USAGE
    synthetic = synth.danger_ok
    sim = sim_requested(args.sim)
    if synthetic and (sim or args.ad3):
        _err("sadi: --synthetic-specimen cannot be combined with --sim or --ad3\n")
        return EXIT_USAGE
    if not args.skip_preflight:
        pre = preflight(data_root, port)
        if pre.is_err:
            _err(pre.danger_err)
            _err("sadi: doctor preflight failed; follow the steps above, then retry.\n")
            return EXIT_PREFLIGHT
    device: DeviceService | None = None
    if synthetic:
        device = _open_synthetic()
        _out(SYNTHETIC_BANNER)
    elif sim:
        _log.info("simulator mode requested")
        opened = open_sim_device()
        if opened.is_err:
            _err(f"sadi: {opened.danger_err}\n")
            return EXIT_DEVICE
        device = opened.danger_ok
    from sadi.bench.ad3.launch import ad3_requested, open_managed_ad3

    if device is None and not synthetic and not ad3_requested(args.ad3):
        from sadi.server.device_open import (
            open_real_device,
            resolve_device_port,
            unopened_real_device,
        )

        dev_port = resolve_device_port(args.device_port)
        _log.info("opening the real SADI board on %s", dev_port)
        real = open_real_device(dev_port)
        if real.is_err:
            # frob:ticket 01M7242CRQGBYWTR080XEYNFS9
            _log.warning("real board unavailable; starting with no device: %s", real.danger_err)
            _err(f"sadi: WARNING: {real.danger_err}\n")
            _err(NO_DEVICE_BANNER)
            # frob:ticket 01M724AKWJV8BRNRR3Q43553VR
            device = unopened_real_device(dev_port)
        else:
            device = real.danger_ok

    ad3: Ad3Guard | None = None
    if ad3_requested(args.ad3):
        _log.info("ad3 requested")
        got_ad3 = open_managed_ad3()
        if got_ad3.is_err:
            _err(f"sadi: {got_ad3.danger_err}\n")
            if device is not None:
                device.close()
            return EXIT_AD3
        ad3 = got_ad3.danger_ok
    try:
        return _serve_app(args, serve, data_root, port, device, synthetic)
    finally:
        if ad3 is not None:
            ad3.close()


#: Printed when real mode starts with no board: browse and export only, capture stays blocked.
NO_DEVICE_BANNER: Final[str] = (
    "sadi: no instrument attached: starting anyway so closed sessions can be browsed and "
    "exported; status is disconnected and capture is blocked until a board is attached "
    "(plug it in and restart sadi). No session is created or changed.\n"
)


def _serve_app(
    args: argparse.Namespace,
    serve: Serve,
    data_root: Path,
    port: int,
    device: DeviceService | None,
    synthetic: bool = False,
) -> int:
    """Build the app, mount the web and serve; return the exit code."""
    from sadi.core.pipeline import Bus
    from sadi.server.app import AppSettings, RootLockStartupError, create_app
    from sadi.server.live import LiveAcquisition

    plugins, labs = load_builtin_plugins()
    # frob:ticket 01M720QDHPFPD9CNEADS1CA9V6
    if not synthetic and device is not None and device.status == "simulated":
        synthetic = True
        _log.warning("simulator device: sessions and exports are labelled SYNTHETIC, not real")
        _out("sadi: simulator in use: all data is SIMULATED and will be labelled SYNTHETIC\n")
    live = LiveAcquisition(device, Bus()) if device is not None else None
    app = create_app(
        AppSettings(
            data_root=data_root,
            recover_stale=bool(args.recover_stale),
            device=device,
            registry=plugins,
            labs=labs,
            bus=live.bus if live is not None else None,
            live=live,
            synthetic=synthetic,
        )
    )
    mount_web(app, resolve_web_dist(args.web_dist))
    _out(f"sadi: serving at http://{args.host}:{port}/\n")
    if not args.no_browser:
        schedule_browser(args.host, port)
    _log.info("starting server on %s:%d", args.host, port)
    try:
        serve(app, args.host, port)
    except RootLockStartupError as exc:
        _log.error("data-root lock refused: %s", exc)
        _err(f"sadi: {exc}\n")
        return EXIT_LOCK
    except KeyboardInterrupt:
        _log.info("interrupted; server shut down gracefully")
        _out("sadi: stopped\n")
    finally:
        if device is not None:
            device.close()
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
