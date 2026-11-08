"""Probes: the only door from a check to the OS, so tests can swap in a fake world."""

# frob:ticket 01M6WA9WYE9D71BBA7AV3H5CGF
from __future__ import annotations

import errno
import importlib
import importlib.metadata
import locale
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Literal, Protocol

from typani import Err, Ok, Result

from sadi.doctor.schema import CommandRun, Os, ProbeError
from sadi.doctor.sessions import SessionFacts, survey_sessions
from sadi.logging_setup import get_logger
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

    def browser_available(self) -> bool:
        """Return True when a browser controller can be resolved."""
        ...

    def plugin_findings(self) -> list[DoctorFinding]:
        """Return the plugin doctor findings for the installed plugins."""
        ...


class RealProbes:
    """Probes over the real machine; read-only by construction."""

    def __init__(self) -> None:
        """Start with an empty per-run session survey cache."""
        self._sessions: dict[tuple[str, bool], list[SessionFacts]] = {}

    def session_facts(self, data_root: str, deep: bool) -> list[SessionFacts]:
        """Survey sessions read-only via the store APIs, once per (root, deep) per run."""
        key = (data_root, deep)
        if key not in self._sessions:
            self._sessions[key] = survey_sessions(data_root, deep)
        return self._sessions[key]

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
        return Os.WSL if text and "microsoft" in text.lower() else Os.LINUX

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
        """Return the longest-prefix mount's fstype from /proc/mounts (Linux/WSL), else None."""
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
            return importlib.metadata.metadata(name).get("Requires-Python")
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

    def web_bundle(self) -> tuple[bool, int]:
        """Look for sadi/web/dist/index.html next to the package."""
        index = Path(__file__).resolve().parent.parent / "web" / "dist" / "index.html"
        try:
            return index.is_file(), index.stat().st_size if index.is_file() else 0
        except OSError:
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
