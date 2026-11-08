"""In-memory Probes for doctor tests: a healthy Linux box that tests break one fact at a time."""

# frob:ticket 01M6WA9WYE9D71BBA7AV3H5CGF
from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from typani import Err, Ok, Result

from sadi.doctor.checks import ext, net, usb
from sadi.doctor.devprobe import DeviceFacts, SimFacts
from sadi.doctor.schema import CommandRun, Os, ProbeError
from sadi.doctor.sessions import SessionFacts
from sadi.doctor.volprobe import FlushFacts, LockState
from sadi.doctor.workerprobe import WorkerFacts
from sadi.plugins.doctor import DoctorFinding

GIB = 1024**3


HEALTHY_DEVICE = DeviceFacts(
    ports=("/dev/ttyUSB0",),
    port="/dev/ttyUSB0",
    open_status="ok",
    query_status="ok",
    fw_version="3.410",
    state="stopped",
    state_byte=2,
    stream_status="ok",
    packets_per_s=1000.0,
    boot_status="ok",
    boot_seconds=1.0,
)


@dataclass
class FakeProbes:
    """Every probe answers from a field; defaults describe a fully healthy Linux machine."""

    os: Os = Os.LINUX
    py: tuple[int, int, int] = (3, 12, 3)
    environ: dict[str, str] = field(default_factory=dict)
    tools: dict[str, str] = field(default_factory=lambda: {"uv": "/usr/bin/uv"})
    commands: dict[str, Result[CommandRun, ProbeError]] = field(default_factory=dict)
    files: dict[str, str] = field(default_factory=dict)
    dirs: dict[str, list[str]] = field(default_factory=dict)
    links: dict[str, str] = field(default_factory=dict)
    read_only: set[str] = field(default_factory=set)
    dists: dict[str, str] = field(
        default_factory=lambda: {
            "sadi": "0.1.0",
            "pydantic": "2.9.0",
            "typani": "1.0",
            "fastapi": "0.1",
            "uvicorn": "0.1",
            "numpy": "2.0",
            "crc32c": "2.0",
        }
    )
    requires: dict[str, str] = field(default_factory=lambda: {"sadi": ">=3.11"})
    import_errors: dict[str, str] = field(default_factory=dict)
    bind: str = "free"
    loopback: bool = True
    localhost: list[str] = field(default_factory=lambda: ["127.0.0.1", "::1"])
    bundle: tuple[bool, int] = (True, 2048)
    integrity: tuple[list[str], list[str]] = field(default_factory=lambda: ([], []))
    clock: float = 1_800_000_000.0
    cpus: int = 8
    mem: int | None = 8 * GIB
    nofile: int | None = 4096
    enc: tuple[str, bool] = ("utf-8", False)
    groups: list[str] = field(default_factory=lambda: ["users", "dialout"])
    node_ok: tuple[bool, str | None] = (True, "dialout")
    data_dir: str = "/home/u/.local/share/sadi"
    free: int | None = 100 * GIB
    fs: str | None = "ext4"
    flush: FlushFacts = field(default_factory=FlushFacts)
    lock: LockState = "ok"
    sizes: dict[str, int] = field(default_factory=dict)
    battery: bool | None = False
    mono_res: float = 1e-9
    tz: str | None = "UTC"
    spills: list[str] = field(default_factory=list)
    sessions: list[SessionFacts] = field(default_factory=list)
    browser: bool = True
    mach: str = "x86_64"
    target: str | None = "x86_64-unknown-linux-gnu"
    long_paths: bool | None = True
    web_ver: str | None = "0.1.0"
    browser_ver: tuple[str, int] | None = ("firefox", 120)
    launch_hit: bool = True
    findings: list[DoctorFinding] = field(default_factory=list)
    device: DeviceFacts = field(default_factory=DeviceFacts)
    sim: SimFacts = field(default_factory=SimFacts)
    workers: WorkerFacts = field(default_factory=WorkerFacts)

    def os_kind(self) -> Os:
        """Return the fake OS."""
        return self.os

    def os_version(self) -> str:
        """Return a fixed release string."""
        return "fake-1.0"

    def machine(self) -> str:
        """Return the fake arch."""
        return self.mach

    def py_version(self) -> tuple[int, int, int]:
        """Return the fake Python version."""
        return self.py

    def env(self) -> Mapping[str, str]:
        """Return the fake environment."""
        return self.environ

    def which(self, name: str) -> str | None:
        """Return the fake tool path."""
        return self.tools.get(name)

    def run(self, argv: Sequence[str], timeout: float = 5.0) -> Result[CommandRun, ProbeError]:
        """Return the canned result keyed by the last argv words, or exit 0."""
        key = " ".join(argv[1:]) if len(argv) > 1 else argv[0]
        canned = self.commands.get(key)
        if canned is not None:
            return canned
        return Ok(CommandRun(argv=tuple(argv), exit_code=0))

    def exists(self, path: str) -> bool:
        """Report whether the path is a known file, dir or link."""
        return path in self.files or path in self.dirs or path in self.links

    def is_dir(self, path: str) -> bool:
        """Report whether the path is a known dir."""
        return path in self.dirs

    def writable(self, path: str) -> bool:
        """Report writability."""
        return path not in self.read_only

    def read_text(self, path: str) -> str | None:
        """Return fake file text."""
        return self.files.get(path)

    def listdir(self, path: str) -> list[str] | None:
        """Return fake directory entries."""
        return self.dirs.get(path)

    def node_access(self, path: str) -> tuple[bool, str | None]:
        """Return the fake node access."""
        return self.node_ok

    def disk_free(self, path: str) -> int | None:
        """Return fake free bytes."""
        return self.free

    def fstype(self, path: str) -> str | None:
        """Return the fake filesystem type."""
        return self.fs

    def build_target(self) -> str | None:
        """Return the fake sadi_py build target."""
        return self.target

    def long_paths_enabled(self) -> bool | None:
        """Return the fake LongPathsEnabled value."""
        return self.long_paths

    def web_bundle_version(self) -> str | None:
        """Return the fake bundle version."""
        return self.web_ver

    def browser_version(self) -> tuple[str, int] | None:
        """Return the fake default browser (family, major)."""
        return self.browser_ver

    def browser_launch_hit(self, timeout: float) -> bool:
        """Return whether the fake browser fetched the throwaway page."""
        return self.launch_hit

    def dist_version(self, name: str) -> str | None:
        """Return the fake distribution version."""
        return self.dists.get(name)

    def requires_python(self, name: str) -> str | None:
        """Return the fake Requires-Python."""
        return self.requires.get(name)

    def python_exe(self) -> str:
        """Return a fixed interpreter path."""
        return "/venv/bin/python"

    def readlink(self, path: str) -> str | None:
        """Return the fake link target."""
        return self.links.get(path)

    def import_error(self, module: str) -> str | None:
        """Return the fake import error text, or None when it imports."""
        return self.import_errors.get(module)

    def bind_state(self, port: int) -> str:
        """Return the fake bind state."""
        return self.bind

    def loopback_ok(self) -> bool:
        """Return the fake loopback result."""
        return self.loopback

    def localhost_addrs(self) -> list[str]:
        """Return the fake localhost addresses."""
        return self.localhost

    def package_integrity(self) -> tuple[list[str], list[str]]:
        """Return the fake (modified, missing) integrity findings."""
        return self.integrity

    def web_bundle(self) -> tuple[bool, int]:
        """Return the fake bundle state."""
        return self.bundle

    def now(self) -> float:
        """Return the fake clock."""
        return self.clock

    def cpu_count(self) -> int:
        """Return the fake CPU count."""
        return self.cpus

    def mem_available(self) -> int | None:
        """Return the fake available memory."""
        return self.mem

    def nofile_soft(self) -> int | None:
        """Return the fake open-file limit."""
        return self.nofile

    def flush_facts(self, data_root: str) -> FlushFacts:
        """Return the fake flush facts."""
        return self.flush

    def lock_state(self, target: str) -> LockState:
        """Return the fake lock state."""
        return self.lock

    def file_size(self, path: str) -> int | None:
        """Return the fake size, falling back to the fake file text length."""
        if path in self.sizes:
            return self.sizes[path]
        return len(self.files[path]) if path in self.files else None

    def on_battery(self) -> bool | None:
        """Return the fake battery state."""
        return self.battery

    def monotonic_resolution(self) -> float:
        """Return the fake clock resolution."""
        return self.mono_res

    def tz_name(self) -> str | None:
        """Return the fake timezone name."""
        return self.tz

    def encoding(self) -> tuple[str, bool]:
        """Return the fake encoding."""
        return self.enc

    def user_groups(self) -> list[str]:
        """Return the fake group list."""
        return self.groups

    def user_data_dir(self) -> str:
        """Return the fake default data dir."""
        return self.data_dir

    def session_facts(self, data_root: str, deep: bool) -> list[SessionFacts]:
        """Return the fake session survey."""
        return self.sessions

    def spill_files(self, data_root: str) -> list[str]:
        """Return the fake spill files."""
        return self.spills

    def device_facts(self, port: str | None, stream_seconds: int, with_reset: bool) -> DeviceFacts:
        """Return the fake device facts."""
        return self.device

    def sim_facts(self) -> SimFacts:
        """Return the fake simulator facts."""
        return self.sim

    def worker_facts(self) -> WorkerFacts:
        """Return the fake worker facts."""
        return self.workers

    def browser_available(self) -> bool:
        """Return the fake browser availability."""
        return self.browser

    def plugin_findings(self) -> list[DoctorFinding]:
        """Return the fake plugin findings."""
        return self.findings


def healthy() -> FakeProbes:
    """Return a healthy Linux machine with a present, writable data root and a plugged-in board."""
    p = FakeProbes()
    p.dirs[p.data_dir] = []
    p.dirs["/sys/bus/usb/devices"] = ["1-1", "1-1:1.0"]
    p.files["/sys/bus/usb/devices/1-1/idVendor"] = "0403\n"
    p.files["/sys/bus/usb/devices/1-1/idProduct"] = "6010\n"
    p.links["/sys/bus/usb/devices/1-1/1-1:1.0/driver"] = "../../../bus/usb/drivers/ftdi_sio"
    p.dirs["/dev"] = ["ttyUSB0", "cu.usbserial-FT1", "null"]
    p.tools.update(
        {
            "usbipd.exe": "/usbipd.exe",
            "system_profiler": "/usr/sbin/system_profiler",
            "powershell": "powershell.exe",
        }
    )
    p.files["/sys/bus/usb-serial/devices/ttyUSB0/latency_timer"] = "2\n"
    p.device = HEALTHY_DEVICE
    p.files["/venv/pyvenv.cfg"] = "home = /usr/bin\n"
    p.commands.update(
        {
            "-c " + ext.INFO_SCRIPT: _json(
                {"version": "0.1.0", "protocol": 1, "expected_protocol": 1}
            ),
            "-c " + ext.VCRUNTIME_SCRIPT: _json([]),
            "-c " + ext.FEATURES_SCRIPT: _json(["udev"]),
            "SPUSBDataType": _out("Product ID: 0x6010\n Vendor ID: 0x0403\n"),
            ps(usb.PS_FTDI): _out("USB\\VID_0403&PID_6010\\FT1\n"),
            ps(usb.PS_VCP_PORTS): _out("USB Serial Port (COM3)\n"),
            ps(usb.PS_VCP_STATUS): _out("OK\n"),
            ps(usb.PS_PORT_NAMES): _out("COM3\n"),
            "show -p NTPSynchronized": _out("NTPSynchronized=yes\n"),
            "-c " + net.health_script(8000): _json({"status": 200, "version": "0.1.0"}),
        }
    )
    return p


def ps(script: str) -> str:
    """Return the canned-command key of a PowerShell one-liner."""
    return "-NoProfile -NonInteractive -Command " + script


def _out(text: str) -> Result[CommandRun, ProbeError]:
    """Build a canned run whose stdout is the given text."""
    return Ok(CommandRun(argv=("cmd",), exit_code=0, stdout_tail=text))


def _json(value: object) -> Result[CommandRun, ProbeError]:
    """Build a canned child run whose stdout is the JSON value."""
    return Ok(CommandRun(argv=("py",), exit_code=0, stdout_tail=json.dumps(value)))


_ = Err  # kept for tests that inject probe errors
