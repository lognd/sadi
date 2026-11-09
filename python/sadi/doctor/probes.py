"""Probes: the only door from a check to the OS, so tests can swap in a fake world."""

# frob:ticket 01M6WA9WYE9D71BBA7AV3H5CGF
from __future__ import annotations

import base64
import errno
import hashlib
import importlib
import importlib.metadata
import locale
import os
import platform
import shutil
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol

from typani import Err, Ok, Result

from sadi.doctor import hostprobe
from sadi.doctor.devprobe import DeviceFacts, SimFacts, probe_device, probe_sim
from sadi.doctor.schema import CommandRun, Os, ProbeError
from sadi.doctor.sessions import SessionFacts, survey_sessions
from sadi.doctor.volprobe import FlushFacts, LockState, probe_flush, probe_lock
from sadi.doctor.workerprobe import WorkerFacts, probe_workers
from sadi.logging_setup import get_logger

if TYPE_CHECKING:
    from sadi.plugins.doctor import DoctorFinding

_log = get_logger(__name__)

TAIL_BYTES = 2048
DEFAULT_TIMEOUT_S = 5.0

BindState = Literal["free", "in-use", "denied"]


class Probes(Protocol):
    """Read-only view of the host; every method is a pure observation."""

    def os_kind(self) -> Os:
        """Return the detected OS, WSL distinct from Linux."""
        ...

    def os_version(self) -> str:
        """Return a human OS release string."""
        ...

    def machine(self) -> str:
        """Return the CPU architecture."""
        ...

    def py_version(self) -> tuple[int, int, int]:
        """Return the interpreter version triple."""
        ...

    def env(self) -> Mapping[str, str]:
        """Return the process environment."""
        ...

    def which(self, name: str) -> str | None:
        """Return the path of an executable on PATH, or None."""
        ...

    def run(
        self, argv: Sequence[str], timeout: float = DEFAULT_TIMEOUT_S
    ) -> Result[CommandRun, ProbeError]:
        """Run a fixed-argv read-only command without a shell."""
        ...

    def exists(self, path: str) -> bool:
        """Return True when the path exists."""
        ...

    def is_dir(self, path: str) -> bool:
        """Return True when the path is a directory."""
        ...

    def writable(self, path: str) -> bool:
        """Return True when the current user may write the path (no probe file is made)."""
        ...

    def read_text(self, path: str) -> str | None:
        """Return file text, or None when unreadable."""
        ...

    def listdir(self, path: str) -> list[str] | None:
        """Return directory entry names, or None when unreadable."""
        ...

    def node_access(self, path: str) -> tuple[bool, str | None]:
        """Return (user can read+write, owning group name) for a device node."""
        ...

    def disk_free(self, path: str) -> int | None:
        """Return free bytes on the volume holding the path (nearest existing parent)."""
        ...

    def fstype(self, path: str) -> str | None:
        """Return the filesystem type holding the path, lowercase."""
        ...

    def dist_version(self, name: str) -> str | None:
        """Return an installed distribution's version, or None."""
        ...

    def requires_python(self, name: str) -> str | None:
        """Return an installed distribution's Requires-Python specifier, or None."""
        ...

    def python_exe(self) -> str:
        """Return the interpreter path used for isolated import subprocesses."""
        ...

    def readlink(self, path: str) -> str | None:
        """Return a symlink target, or None when not a link."""
        ...

    def import_error(self, module: str) -> str | None:
        """Import a module in-process; return None on success else the error text."""
        ...

    def bind_state(self, port: int) -> BindState:
        """Try to bind 127.0.0.1:port and release it at once."""
        ...

    def loopback_ok(self) -> bool:
        """Round-trip one byte over the loopback interface."""
        ...

    def localhost_addrs(self) -> list[str]:
        """Return what `localhost` resolves to."""
        ...

    def package_integrity(self) -> tuple[list[str], list[str]]:
        """Return (modified, missing) sampled sadi files by RECORD hash; read-only."""
        ...

    def web_bundle(self) -> tuple[bool, int]:
        """Return (index.html exists, its size in bytes) for the packaged UI."""
        ...

    def now(self) -> float:
        """Return wall-clock epoch seconds."""
        ...

    def cpu_count(self) -> int:
        """Return logical CPU count."""
        ...

    def mem_available(self) -> int | None:
        """Return available RAM in bytes, or None when unknown."""
        ...

    def nofile_soft(self) -> int | None:
        """Return the soft open-file limit (POSIX), or None."""
        ...

    def encoding(self) -> tuple[str, bool]:
        """Return (preferred encoding, UTF-8 mode on)."""
        ...

    def flush_facts(self, data_root: str) -> FlushFacts:
        """Create, fsync and delete one probe file under <root>/doctor/ (opt-in only)."""
        ...

    def lock_state(self, target: str) -> LockState:
        """Try a non-blocking shared lock on a read-only descriptor of target."""
        ...

    def file_size(self, path: str) -> int | None:
        """Return a file's size in bytes, or None when unreadable."""
        ...

    def on_battery(self) -> bool | None:
        """Return True when running on battery, False on mains, None without a battery."""
        ...

    def monotonic_resolution(self) -> float:
        """Return the monotonic clock resolution in seconds."""
        ...

    def tz_name(self) -> str | None:
        """Return the local timezone name, or None when it cannot be resolved."""
        ...

    def user_groups(self) -> list[str]:
        """Return the group names of the current user."""
        ...

    def user_data_dir(self) -> str:
        """Return the default per-user SADI data directory."""
        ...

    def spill_files(self, data_root: str) -> list[str]:
        """Return emergency spill files found for the data root."""
        ...

    def session_facts(self, data_root: str, deep: bool) -> list[SessionFacts]:
        """Return a read-only survey of every session under the data root."""
        ...

    def device_facts(self, port: str | None, stream_seconds: int, with_reset: bool) -> DeviceFacts:
        """Return what one read-only session against the board observed (no board: no-device)."""
        ...

    def sim_facts(self) -> SimFacts:
        """Return the simulator connect-sequence and scenario-sweep facts."""
        ...

    def worker_facts(self) -> WorkerFacts:
        """Return what spawning a worker and orphaning a watchdog child observed."""
        ...

    def build_target(self) -> str | None:
        """Return the target tag baked into sadi_py at build, or None when it has none."""
        ...

    def long_paths_enabled(self) -> bool | None:
        """Return the Windows LongPathsEnabled registry flag, None when not Windows."""
        ...

    def web_bundle_version(self) -> str | None:
        """Return the SADI version recorded in dist/version.json, None when absent."""
        ...

    def browser_version(self) -> tuple[str, int] | None:
        """Return (family, major version) of the default browser, None when unknown."""
        ...

    def browser_launch_hit(self, timeout: float) -> bool:
        """Open the browser at a throwaway local listener; True when it fetched the page."""
        ...

    def browser_available(self) -> bool:
        """Return True when a browser controller can be resolved."""
        ...

    def plugin_findings(self) -> list[DoctorFinding]:
        """Return the plugin doctor findings for the installed plugins."""
        ...


_INTEGRITY_PREFIXES = ("sadi/doctor/", "sadi/store/")
_INTEGRITY_FILES = ("sadi/web/dist/index.html",)


def _record_integrity() -> tuple[list[str], list[str]]:
    """Compare sampled RECORD sha256 entries with the files on disk; editable installs yield none."""
    try:
        dist = importlib.metadata.distribution("sadi")
    except importlib.metadata.PackageNotFoundError:
        return [], []
    modified: list[str] = []
    missing: list[str] = []
    for entry in dist.files or []:
        rel = entry.as_posix()
        sampled = rel.startswith(_INTEGRITY_PREFIXES) or rel in _INTEGRITY_FILES
        if not sampled or "__pycache__" in rel or entry.hash is None or entry.hash.mode != "sha256":
            continue
        path = Path(str(dist.locate_file(entry)))
        try:
            digest = hashlib.sha256(path.read_bytes()).digest()
        except FileNotFoundError:
            missing.append(rel)
            continue
        except OSError:
            _log.warning("integrity: cannot read %s", path)
            continue
        if base64.urlsafe_b64encode(digest).rstrip(b"=").decode() != entry.hash.value:
            modified.append(rel)
    _log.debug("integrity: %d modified, %d missing", len(modified), len(missing))
    return modified, missing


class RealProbes:
    """Probes over the real machine; read-only by construction."""

    def __init__(self) -> None:
        """Start with an empty per-run session survey cache."""
        self._sessions: dict[tuple[str, bool], list[SessionFacts]] = {}
        self._devices: dict[tuple[str | None, int, bool], DeviceFacts] = {}
        self._sim: SimFacts | None = None
        self._workers: WorkerFacts | None = None
        # one lock per cache: checks run in parallel, each survey must run once per run
        self._lock_sessions = threading.Lock()
        self._lock_devices = threading.Lock()
        self._lock_sim = threading.Lock()
        self._lock_workers = threading.Lock()

    def session_facts(self, data_root: str, deep: bool) -> list[SessionFacts]:
        """Survey sessions read-only via the store APIs, once per (root, deep) per run."""
        key = (data_root, deep)
        with self._lock_sessions:
            if key not in self._sessions:
                self._sessions[key] = survey_sessions(data_root, deep)
            return self._sessions[key]

    def device_facts(self, port: str | None, stream_seconds: int, with_reset: bool) -> DeviceFacts:
        """Probe the board once per (port, stream, reset) per run."""
        key = (port, stream_seconds, with_reset)
        with self._lock_devices:
            if key not in self._devices:
                self._devices[key] = probe_device(port, stream_seconds, with_reset)
            return self._devices[key]

    def sim_facts(self) -> SimFacts:
        """Probe the simulator once per run."""
        with self._lock_sim:
            if self._sim is None:
                self._sim = probe_sim()
            return self._sim

    def worker_facts(self) -> WorkerFacts:
        """Spawn the worker probes once per run."""
        with self._lock_workers:
            if self._workers is None:
                self._workers = probe_workers()
            return self._workers

    def os_kind(self) -> Os:
        """Detect the OS; on Linux WSL_DISTRO_NAME or 'microsoft' in /proc/version means WSL."""
        system = platform.system()
        if system == "Windows":
            return Os.WINDOWS
        if system == "Darwin":
            return Os.MACOS
        if "WSL_DISTRO_NAME" in os.environ:
            return Os.WSL
        text = self.read_text("/proc/version")
        return Os.WSL if text is not None and "microsoft" in text.lower() else Os.LINUX

    def os_version(self) -> str:
        """Return platform.platform()."""
        return platform.platform()

    def machine(self) -> str:
        """Return platform.machine()."""
        return platform.machine()

    def py_version(self) -> tuple[int, int, int]:
        """Return sys.version_info[:3]."""
        v = sys.version_info
        return (v.major, v.minor, v.micro)

    def env(self) -> Mapping[str, str]:
        """Return os.environ."""
        return os.environ

    def which(self, name: str) -> str | None:
        """Return shutil.which(name)."""
        return shutil.which(name)

    def run(
        self, argv: Sequence[str], timeout: float = DEFAULT_TIMEOUT_S
    ) -> Result[CommandRun, ProbeError]:
        """Run argv with no shell, stdin closed, a timeout, and capture output tails."""
        started = time.monotonic()
        _log.debug("run %s", list(argv))
        try:
            proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
                list(argv),
                capture_output=True,
                text=True,
                timeout=timeout,
                stdin=subprocess.DEVNULL,
                check=False,
            )
        except FileNotFoundError:
            return Err(ProbeError(kind="tool-missing", detail=f"{argv[0]} not found"))
        except subprocess.TimeoutExpired:
            return Err(ProbeError(kind="timeout", detail=f"{argv[0]} timed out after {timeout}s"))
        except OSError as exc:
            return Err(ProbeError(kind="exception", detail=f"{argv[0]}: {exc}"))
        ms = int((time.monotonic() - started) * 1000)
        _log.debug("run %s -> %d in %d ms", list(argv), proc.returncode, ms)
        return Ok(
            CommandRun(
                argv=tuple(argv),
                exit_code=proc.returncode,
                stdout_tail=proc.stdout[-TAIL_BYTES:],
                stderr_tail=proc.stderr[-TAIL_BYTES:],
                duration_ms=ms,
            )
        )

    def exists(self, path: str) -> bool:
        """Return Path.exists()."""
        return Path(path).exists()

    def is_dir(self, path: str) -> bool:
        """Return Path.is_dir()."""
        return Path(path).is_dir()

    def writable(self, path: str) -> bool:
        """Return os.access(W_OK)."""
        return os.access(path, os.W_OK)

    def read_text(self, path: str) -> str | None:
        """Read a text file, None on any OSError."""
        try:
            return Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

    def listdir(self, path: str) -> list[str] | None:
        """List a directory, None on any OSError."""
        try:
            return sorted(os.listdir(path))
        except OSError:
            return None

    def node_access(self, path: str) -> tuple[bool, str | None]:
        """Check R/W access to a node and name its group (POSIX)."""
        ok = os.access(path, os.R_OK | os.W_OK)
        try:
            import grp

            group = grp.getgrgid(os.stat(path).st_gid).gr_name
        except (ImportError, OSError, KeyError):
            group = None
        return ok, group

    def disk_free(self, path: str) -> int | None:
        """Return free bytes for the nearest existing parent of path."""
        probe = Path(path)
        while not probe.exists() and probe != probe.parent:
            probe = probe.parent
        try:
            return shutil.disk_usage(probe).free
        except OSError:
            return None

    def fstype(self, path: str) -> str | None:
        """Return the longest-prefix mount's fstype from /proc/mounts (Linux/WSL), `mount` (macOS) or Win32."""
        kind = self.os_kind()
        if kind is Os.WINDOWS:
            return hostprobe.windows_fstype(path)
        if kind is Os.MACOS:
            res = self.run(["mount"])
            if not isinstance(res, Ok) or res.value.exit_code != 0:
                return None
            return hostprobe.mount_fstype(res.value.stdout_tail, str(Path(path).resolve()))
        text = self.read_text("/proc/mounts")
        if text is None:
            return None
        real = str(Path(path).resolve())
        best: tuple[int, str] | None = None
        for line in text.splitlines():
            parts = line.split()
            if len(parts) < 3:
                continue
            mount = parts[1]
            if (real == mount or real.startswith(mount.rstrip("/") + "/")) and (
                best is None or len(mount) > best[0]
            ):
                best = (len(mount), parts[2].lower())
        return best[1] if best else None

    def dist_version(self, name: str) -> str | None:
        """Return importlib.metadata.version or None."""
        try:
            return importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            return None

    def requires_python(self, name: str) -> str | None:
        """Return the Requires-Python metadata of a distribution, or None."""
        try:
            return importlib.metadata.metadata(name)["Requires-Python"]
        except importlib.metadata.PackageNotFoundError:
            return None

    def python_exe(self) -> str:
        """Return sys.executable."""
        return sys.executable

    def readlink(self, path: str) -> str | None:
        """Return os.readlink or None."""
        try:
            return os.readlink(path)
        except OSError:
            return None

    def import_error(self, module: str) -> str | None:
        """Import in-process; return the error text or None."""
        try:
            importlib.import_module(module)
        except Exception as exc:  # noqa: BLE001 - any import failure is evidence
            return f"{type(exc).__name__}: {exc}"
        return None

    def bind_state(self, port: int) -> BindState:
        """Bind and immediately close 127.0.0.1:port."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
            except OSError as exc:
                if exc.errno == errno.EADDRINUSE:
                    return "in-use"
                return "denied"
        return "free"

    def loopback_ok(self) -> bool:
        """Connect to a throwaway loopback listener and echo one byte."""
        try:
            with socket.socket() as srv:
                srv.bind(("127.0.0.1", 0))
                srv.listen(1)
                srv.settimeout(2)
                with socket.create_connection(srv.getsockname(), timeout=2) as cli:
                    conn, _ = srv.accept()
                    with conn:
                        cli.sendall(b"x")
                        return conn.recv(1) == b"x"
        except OSError:
            return False

    def localhost_addrs(self) -> list[str]:
        """Resolve localhost."""
        try:
            return sorted({str(i[4][0]) for i in socket.getaddrinfo("localhost", None)})
        except OSError:
            return []

    def package_integrity(self) -> tuple[list[str], list[str]]:
        """Hash the sampled sadi files against the installed RECORD (never writes)."""
        return _record_integrity()

    def web_bundle(self) -> tuple[bool, int]:
        """Look for index.html in the packaged sadi/_ui, else the repo web/dist (as the launcher does)."""
        pkg = Path(__file__).resolve().parent.parent
        for index in (
            pkg / "_ui" / "index.html",
            pkg.parent.parent / "web" / "dist" / "index.html",
        ):
            try:
                if index.is_file() and index.stat().st_size > 0:
                    return True, index.stat().st_size
            except OSError:
                continue
        return False, 0

    def now(self) -> float:
        """Return time.time()."""
        return time.time()

    def cpu_count(self) -> int:
        """Return os.cpu_count() or 1."""
        return os.cpu_count() or 1

    def mem_available(self) -> int | None:
        """Return psutil available memory, or None when psutil cannot say."""
        try:
            import psutil

            return int(psutil.virtual_memory().available)
        except Exception:  # noqa: BLE001 - psutil is optional evidence
            return None

    def nofile_soft(self) -> int | None:
        """Return RLIMIT_NOFILE soft limit on POSIX."""
        try:
            import resource

            return resource.getrlimit(resource.RLIMIT_NOFILE)[0]
        except (ImportError, ValueError, OSError):
            return None

    def flush_facts(self, data_root: str) -> FlushFacts:
        """Run the flush probe (the only writer, gated by --allow-probe-write in the check)."""
        return probe_flush(data_root)

    def lock_state(self, target: str) -> LockState:
        """Probe a shared lock on target."""
        return probe_lock(target)

    def file_size(self, path: str) -> int | None:
        """Return os.stat size, None on OSError."""
        try:
            return os.stat(path).st_size
        except OSError:
            return None

    def on_battery(self) -> bool | None:
        """Return psutil's battery state: True when discharging, None without a battery."""
        try:
            import psutil

            sensors = getattr(psutil, "sensors_battery", None)
            battery = sensors() if sensors is not None else None
        except Exception:  # noqa: BLE001 - psutil is optional evidence
            return None
        if battery is None or battery.power_plugged is None:
            return None
        return not battery.power_plugged

    def monotonic_resolution(self) -> float:
        """Return time.get_clock_info('monotonic').resolution."""
        return time.get_clock_info("monotonic").resolution

    def tz_name(self) -> str | None:
        """Return the local tzinfo name, or None when empty."""
        return datetime.now().astimezone().tzname() or None

    def encoding(self) -> tuple[str, bool]:
        """Return (preferred encoding, utf8 mode)."""
        return locale.getpreferredencoding(False), bool(sys.flags.utf8_mode)

    def user_groups(self) -> list[str]:
        """Return group names of the current process."""
        names: list[str] = []
        if not hasattr(os, "getgroups"):
            return names
        import grp

        for gid in os.getgroups():
            try:
                names.append(grp.getgrgid(gid).gr_name)
            except KeyError:
                continue
        return sorted(set(names))

    def user_data_dir(self) -> str:
        """Return the store's per-user data directory."""
        from sadi.store.spill import user_data_dir

        return str(user_data_dir())

    def spill_files(self, data_root: str) -> list[str]:
        """Return spill files via the store's discovery (read-only)."""
        from sadi.store.spill import discover_spills

        return [str(p) for p in discover_spills(Path(data_root))]

    def build_target(self) -> str | None:
        """Return sadi_py.BUILD_TARGET when exposed."""
        return hostprobe.build_target()

    def long_paths_enabled(self) -> bool | None:
        """Read LongPathsEnabled from the Windows registry."""
        return hostprobe.windows_long_paths()

    def web_bundle_version(self) -> str | None:
        """Read dist/version.json next to the package."""
        return hostprobe.web_bundle_version()

    def browser_version(self) -> tuple[str, int] | None:
        """Resolve the default browser and read its major version per OS."""
        kind = self.os_kind()
        if kind is Os.WINDOWS:
            return hostprobe.windows_default_browser()
        name = self._browser_name()
        family = hostprobe.family_of(name) if name is not None and name else None
        if name is None or not name or family is None:
            return None
        if kind is Os.MACOS and family == "safari":
            plist = "/Applications/Safari.app/Contents/Info"
            res = self.run(["defaults", "read", plist, "CFBundleShortVersionString"])
        else:
            exe = self.which(name)
            if exe is None:
                return None
            res = self.run([exe, "--version"])
        if not isinstance(res, Ok) or res.value.exit_code != 0:
            return None
        major = hostprobe.major_version(res.value.stdout_tail)
        return (family, major) if major is not None else None

    def _browser_name(self) -> str | None:
        """Return the executable name of the controller webbrowser would use."""
        import webbrowser

        try:
            return Path(getattr(webbrowser.get(), "name", "") or "").name or None
        except webbrowser.Error:
            return None

    def browser_launch_hit(self, timeout: float) -> bool:
        """Run the launch dry run against a throwaway loopback listener."""
        return hostprobe.launch_hit(timeout)

    def browser_available(self) -> bool:
        """Return True when webbrowser resolves a controller."""
        import webbrowser

        try:
            webbrowser.get()
        except webbrowser.Error:
            return False
        return True

    def plugin_findings(self) -> list[DoctorFinding]:
        """Discover plugins with the standard sources and run the plugin doctor."""
        from sadi.cli.plugins import default_sources
        from sadi.plugins.doctor import check_plugins
        from sadi.plugins.registry import PluginRegistry
        from sadi.plugins.settings import PluginSettings

        settings = PluginSettings()
        registry = PluginRegistry.discover(default_sources(settings), frozenset())
        return check_plugins(registry)
