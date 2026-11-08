"""Doctor tests: per-mode fault injection with remediation text, catalog invariants, read-only lint."""

# frob:ticket 01M6WA9WYE9D71BBA7AV3H5CGF
from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path

import pytest
from doctor_fakes import HEALTHY_DEVICE, FakeProbes, healthy, ps
from typani import Err, Ok

import sadi.doctor as doctor
from sadi.doctor import cli, hostprobe
from sadi.doctor.checks import ext, net, usb
from sadi.doctor.devprobe import DeviceFacts, SimFacts
from sadi.doctor.registry import all_checks, get_remedy
from sadi.doctor.render_text import render
from sadi.doctor.schema import (
    CommandRun,
    DoctorReport,
    Layer,
    Mutates,
    Os,
    ProbeError,
    RunOptions,
    Severity,
    SkipReason,
    Status,
    StepKind,
)
from sadi.doctor.sessions import SessionFacts
from sadi.doctor.volprobe import FlushFacts, LockState
from sadi.doctor.workerprobe import WorkerFacts
from sadi.plugins.doctor import DoctorFinding
from sadi.plugins.doctor import Severity as FSev

ROOT = "/home/u/.local/share/sadi"
SYS = "/sys/bus/usb/devices"
Mut = Callable[[FakeProbes], None]


def _import_fail(stderr: str, code: int = 1) -> Mut:
    def f(p: FakeProbes) -> None:
        p.commands["-c import sadi_py"] = Ok(
            CommandRun(argv=("py",), exit_code=code, stderr_tail=stderr)
        )

    return f


def _child(script: str, value: object) -> Mut:
    def f(p: FakeProbes) -> None:
        p.commands["-c " + script] = Ok(
            CommandRun(argv=("py",), exit_code=0, stdout_tail=json.dumps(value))
        )

    return f


def _child_run(script: str, code: int, stderr: str = "") -> Mut:
    def f(p: FakeProbes) -> None:
        p.commands["-c " + script] = Ok(
            CommandRun(argv=("py",), exit_code=code, stderr_tail=stderr)
        )

    return f


def _both(*muts: Mut) -> Mut:
    def f(p: FakeProbes) -> None:
        for m in muts:
            m(p)

    return f


def _out_cmd(key: str, text: str) -> Mut:
    """Mutator: canned stdout for the command whose argv tail is key."""

    def f(p: FakeProbes) -> None:
        p.commands[key] = Ok(CommandRun(argv=("c",), exit_code=0, stdout_tail=text))

    return f


def _with_config(lock: LockState = "ok", text: str = "") -> Mut:
    """Mutator: a config.toml under the root with the given text and lock state."""

    def f(p: FakeProbes) -> None:
        p.files[f"{ROOT}/config.toml"] = text
        p.lock = lock

    return f


def _logs(writable: bool = True, size: int = 10) -> Mut:
    """Mutator: a logs directory holding one file of the given size."""

    def f(p: FakeProbes) -> None:
        p.dirs[f"{ROOT}/logs"] = ["sadi.log"]
        p.files[f"{ROOT}/logs/sadi.log"] = ""
        p.sizes[f"{ROOT}/logs/sadi.log"] = size
        if not writable:
            p.read_only.add(f"{ROOT}/logs")

    return f


def _sharing(p: FakeProbes) -> None:
    """Mutator: a log that mentions a sharing violation."""
    p.dirs[f"{ROOT}/logs"] = ["a.log"]
    p.files[f"{ROOT}/logs/a.log"] = "x DurableSharingViolation y"


def _set(**kw: object) -> Mut:
    def f(p: FakeProbes) -> None:
        for k, v in kw.items():
            setattr(p, k, v)

    return f


def _priv(p: FakeProbes) -> None:
    p.bind = "denied"


def _drop_root(p: FakeProbes) -> None:
    p.dirs.pop(ROOT)


def _file_root(p: FakeProbes) -> None:
    p.dirs.pop(ROOT)
    p.files[ROOT] = ""


def _ro_root(p: FakeProbes) -> None:
    p.read_only.add(ROOT)


def _no_usb(p: FakeProbes) -> None:
    p.dirs[SYS] = []


def _odd_pid(p: FakeProbes) -> None:
    p.files[f"{SYS}/1-1/idProduct"] = "9999\n"


def _no_driver(p: FakeProbes) -> None:
    p.links.clear()


def _no_node(p: FakeProbes) -> None:
    p.dirs["/dev"] = ["null"]


def _usbipd(state: str) -> Mut:
    def f(p: FakeProbes) -> None:
        p.dirs[SYS] = []
        p.tools["usbipd.exe"] = "/usbipd.exe"
        p.commands["list"] = Ok(
            CommandRun(
                argv=("usbipd.exe",),
                exit_code=0,
                stdout_tail=f"2-3    0403:6010  USB Serial Converter   {state}\n",
            )
        )

    return f


# frob:ticket 01M6WJHVXTWDD0RA55508QAN2W
def _cmd(key: str, text: str) -> Mut:
    """Return a mutator that cans stdout `text` for the command keyed `key`."""

    def f(p: FakeProbes) -> None:
        p.commands[key] = Ok(CommandRun(argv=("cmd",), exit_code=0, stdout_tail=text))

    return f


def _set_file(path: str, text: str) -> Mut:
    """Return a mutator that sets one fake file."""

    def f(p: FakeProbes) -> None:
        p.files[path] = text

    return f


def _all(*muts: Mut) -> Mut:
    """Return a mutator applying several mutators in order."""

    def f(p: FakeProbes) -> None:
        for m in muts:
            m(p)

    return f


def _drop_tool(name: str) -> Mut:
    """Return a mutator removing a tool from PATH."""

    def f(p: FakeProbes) -> None:
        p.tools.pop(name, None)

    return f


def _no_cu(p: FakeProbes) -> None:
    p.dirs["/dev"] = ["null", "ttyUSB0"]


def _wsl_attached(config: str, dmesg: str = "") -> Mut:
    """Return a WSL mutator: attached FTDI row, kernel config text, dmesg text."""
    return _all(
        _cmd("list", "2-3    0403:6010  USB Serial Converter   Attached - Ubuntu\n"),
        _cmd("-E " + usb._KCONFIG + " /proc/config.gz", config),
        _cmd("dmesg", dmesg),
    )


_KCONF_OK = "CONFIG_USB_SERIAL_FTDI_SIO=y\nCONFIG_USB_VHCI_HCD=y\n"


def _no_group(p: FakeProbes) -> None:
    p.node_ok = (False, "dialout")
    p.groups = ["users"]


def _in_group_no_access(p: FakeProbes) -> None:
    p.node_ok = (False, "dialout")


def _sess(*rows: SessionFacts) -> Mut:
    def f(p: FakeProbes) -> None:
        p.sessions = list(rows)

    return f


def _sf(**kw: object) -> SessionFacts:
    base: dict[str, object] = {
        "name": "20261108T153000Z-demo.v001",
        "path": f"{ROOT}/sessions/20261108T153000Z-demo.v001",
        "name_ok": True,
        "family": "20261108T153000Z-demo",
        "version": 1,
        "has_wal": True,
        "segments": 1,
        "manifest": "ok",
        "state": "closed",
        "wal": "ok",
        "last_seq": 3,
    }
    base.update(kw)
    return SessionFacts.model_validate(base)


def _dev(**kw: object) -> Mut:
    def f(p: FakeProbes) -> None:
        p.device = HEALTHY_DEVICE.model_copy(update=kw)

    return f


def _simf(**kw: object) -> Mut:
    def f(p: FakeProbes) -> None:
        p.sim = SimFacts.model_validate(kw)

    return f


def _wrk(**kw: object) -> Mut:
    def f(p: FakeProbes) -> None:
        p.workers = WorkerFacts.model_validate(kw)

    return f


_LONG_ROOT = "C:\\Users\\someone\\" + "d" * 120
_ROOT_FOR = {
    ("PLAT-040", "long-paths-off"): _LONG_ROOT,
    ("PLAT-040", "reserved-name-in-path"): "C:\\Users\\someone\\CON\\sadi",
    ("PLAT-040", "trailing-dot-or-space"): "C:\\Users\\someone\\sadi.",
}

# (check id, mode, os, mutator)
CASES: list[tuple[str, str, Os, Mut]] = [
    ("PLAT-010", "wsl1", Os.WSL, _set(files={"/proc/version": "Linux 4.4.0-Microsoft"})),
    ("PLAT-010", "unsupported-os", Os.WINDOWS, _set(os=Os.WINDOWS)),
    ("PLAT-020", "arch-mismatch", Os.MACOS, _set(mach="arm64", target="x86_64-apple-darwin")),
    ("PLAT-020", "unknown-arch", Os.LINUX, _set(mach="riscv64")),
    ("PLAT-040", "long-paths-off", Os.WINDOWS, _set(long_paths=False)),
    ("PLAT-040", "reserved-name-in-path", Os.WINDOWS, _set()),
    ("PLAT-040", "trailing-dot-or-space", Os.WINDOWS, _set()),
    ("WEB-020", "stale-bundle", Os.LINUX, _set(web_ver="0.0.9")),
    ("BRW-020", "old-browser", Os.LINUX, _set(browser_ver=("firefox", 100))),
    ("BRW-020", "unknown-browser", Os.LINUX, _set(browser_ver=None)),
    ("BRW-030", "launch-no-hit", Os.LINUX, _set(launch_hit=False)),
    ("PLAT-030", "c-locale", Os.LINUX, _set(enc=("ascii", False))),
    ("PLAT-030", "non-utf8-console", Os.WINDOWS, _set(enc=("cp1252", False))),
    ("PLAT-050", "failpoints-armed", Os.LINUX, _set(environ={"SADI_FAILPOINTS": "x"})),
    ("PY-010", "too-old", Os.LINUX, _set(py=(3, 9, 1))),
    ("PY-020", "not-installed", Os.MACOS, _set(dists={})),
    ("PY-030", "missing", Os.WINDOWS, _set(dists={"sadi": "0.1.0"})),
    ("PY-030", "import-error", Os.LINUX, _set(import_errors={"numpy": "boom"})),
    ("PY-030", "pydantic-v1", Os.LINUX, lambda p: p.dists.update(pydantic="1.10.0")),
    ("PY-040", "uv-missing", Os.LINUX, _set(tools={})),
    (
        "EXT-010",
        "not-installed",
        Os.LINUX,
        _import_fail("ModuleNotFoundError: No module named 'sadi_py'"),
    ),
    (
        "EXT-010",
        "abi-mismatch",
        Os.WINDOWS,
        _import_fail("Traceback\nImportError: DLL load failed"),
    ),
    ("EXT-010", "crashed", Os.MACOS, _import_fail("", 139)),
    (
        "EXT-010",
        "timeout",
        Os.LINUX,
        lambda p: p.commands.update(
            {"-c import sadi_py": Err(ProbeError(kind="timeout", detail="20s"))}
        ),
    ),
    (
        "EXT-020",
        "version-mismatch",
        Os.LINUX,
        _child(ext.INFO_SCRIPT, {"version": "0.0.9", "protocol": 1, "expected_protocol": 1}),
    ),
    (
        "EXT-020",
        "protocol-mismatch",
        Os.MACOS,
        _child(ext.INFO_SCRIPT, {"version": "0.1.0", "protocol": 1, "expected_protocol": 2}),
    ),
    ("EXT-030", "missing-vcruntime", Os.WINDOWS, _child(ext.VCRUNTIME_SCRIPT, ["vcruntime140"])),
    ("EXT-040", "no-udev-feature", Os.LINUX, _child(ext.FEATURES_SCRIPT, [])),
    ("EXT-040", "no-udev-feature", Os.WSL, _child(ext.FEATURES_SCRIPT, ["serial"])),
    ("EXT-050", "vectors-fail", Os.LINUX, _child_run(ext.SELFTEST_SCRIPT, 1, "AssertionError")),
    (
        "EXT-050",
        "timeout",
        Os.WINDOWS,
        lambda p: p.commands.update(
            {"-c " + ext.SELFTEST_SCRIPT: Err(ProbeError(kind="timeout", detail="10s"))}
        ),
    ),
    (
        "NET-030",
        "proxy-intercepts-localhost",
        Os.LINUX,
        _set(environ={"HTTPS_PROXY": "http://p:3128"}),
    ),
    ("NET-040", "health-timeout", Os.LINUX, _child(net.health_script(8000), {"status": None})),
    ("NET-040", "health-500", Os.MACOS, _child(net.health_script(8000), {"status": 503})),
    (
        "NET-040",
        "health-version-mismatch",
        Os.WINDOWS,
        _child(net.health_script(8000), {"status": 200, "version": "9.9.9"}),
    ),
    ("PY-050", "wrong-venv", Os.LINUX, _set(environ={"VIRTUAL_ENV": "/other/venv"})),
    ("PY-050", "system-python", Os.MACOS, _set(files={})),
    ("PY-060", "modified-files", Os.LINUX, _set(integrity=(["sadi/doctor/cli.py"], []))),
    ("PY-060", "missing-files", Os.WINDOWS, _set(integrity=([], ["sadi/store/x.py"]))),
    ("WEB-010", "missing-bundle", Os.LINUX, _set(bundle=(False, 0))),
    ("NET-010", "no-loopback", Os.LINUX, _set(loopback=False)),
    ("NET-010", "localhost-not-loopback", Os.WINDOWS, _set(localhost=["10.0.0.5"])),
    ("NET-020", "port-in-use-other", Os.LINUX, _set(bind="in-use")),
    ("NET-020", "port-privileged", Os.LINUX, _priv),
    ("NET-020", "bind-denied", Os.WINDOWS, _set(bind="denied")),
    ("DATA-010", "missing", Os.LINUX, _drop_root),
    ("DATA-010", "not-a-directory", Os.LINUX, _file_root),
    ("DATA-010", "not-writable", Os.MACOS, _ro_root),
    ("DATA-020", "network-fs", Os.LINUX, _set(fs="nfs")),
    ("DATA-020", "drvfs-9p", Os.WSL, _set(fs="9p")),
    ("DATA-020", "fat-exfat", Os.LINUX, _set(fs="vfat")),
    ("DATA-030", "below-minimum", Os.LINUX, _set(free=10**8)),
    ("DATA-030", "low", Os.LINUX, _set(free=5 * 1024**3)),
    (
        "DATA-040",
        "fsync-unsupported",
        Os.LINUX,
        _set(flush=FlushFacts("unsupported", detail="EINVAL")),
    ),
    (
        "DATA-040",
        "fullfsync-fallback",
        Os.MACOS,
        _set(flush=FlushFacts("ok", fullfsync=False, p50_ms=1.0)),
    ),
    ("DATA-040", "fsync-slow", Os.LINUX, _set(flush=FlushFacts("ok", p50_ms=450.0))),
    ("DATA-050", "locks-unsupported", Os.LINUX, _with_config(lock="unsupported")),
    ("DATA-050", "lock-held-by-other", Os.WINDOWS, _with_config(lock="held")),
    ("DATA-060", "not-excluded-from-defender", Os.WINDOWS, _set()),
    ("DATA-060", "indexer-scans-root", Os.MACOS, _out_cmd("-s " + ROOT, "Indexing enabled.")),
    ("DATA-060", "sharing-violations-logged", Os.WINDOWS, _sharing),
    ("DATA-070", "syntax-error", Os.LINUX, _with_config(text="a = = 1")),
    ("DATA-080", "not-writable", Os.LINUX, _logs(writable=False)),
    ("DATA-080", "oversized", Os.WSL, _logs(size=2 * 1024**3)),
    ("CLK-020", "coarse-monotonic", Os.WINDOWS, _set(mono_res=0.0156)),
    ("CLK-030", "tz-unknown", Os.LINUX, _set(tz=None)),
    ("CLK-040", "not-synced", Os.LINUX, _out_cmd("show -p NTPSynchronized", "NTPSynchronized=no")),
    ("CLK-040", "not-synced", Os.MACOS, _out_cmd("-getusingnetworktime", "Network Time: Off")),
    ("RES-040", "on-battery", Os.LINUX, _set(battery=True)),
    (
        "RES-040",
        "usb-selective-suspend",
        Os.WINDOWS,
        _out_cmd(
            "/q SCHEME_CURRENT 2a737441-1930-4402-8d77-b2bebba308a3",
            "Current AC Power Setting Index: 0x00000001",
        ),
    ),
    ("DATA-090", "spill-present", Os.LINUX, _set(spills=["/x/a.spill"])),
    ("USB-020", "no-device", Os.LINUX, _no_usb),
    ("USB-020", "unknown-ftdi-pid", Os.LINUX, _odd_pid),
    ("USB-020", "device-on-windows-side", Os.WSL, _usbipd("Not shared")),
    ("USB-020", "shared-not-attached", Os.WSL, _usbipd("Shared")),
    ("USB-030", "no-driver", Os.LINUX, _no_driver),
    ("USB-040", "node-missing", Os.LINUX, _no_node),
    ("USB-050", "not-in-group", Os.LINUX, _no_group),
    ("USB-050", "node-not-accessible", Os.LINUX, _in_group_no_access),
    ("USB-010", "no-enumeration-tool", Os.MACOS, _drop_tool("system_profiler")),
    ("USB-010", "usbipd-missing", Os.WSL, _drop_tool("usbipd.exe")),
    ("USB-010", "usbipd-old", Os.WSL, _cmd("--version", "usbipd 3.2.0\n")),
    ("USB-020", "no-device", Os.WINDOWS, _cmd(ps(usb.PS_FTDI), "")),
    ("USB-020", "no-device", Os.MACOS, _cmd("SPUSBDataType", "")),
    ("USB-030", "no-driver", Os.WINDOWS, _cmd(ps(usb.PS_VCP_PORTS), "")),
    ("USB-030", "no-driver", Os.MACOS, _no_cu),
    ("USB-040", "node-missing", Os.WINDOWS, _cmd(ps(usb.PS_PORT_NAMES), "")),
    ("USB-050", "node-not-accessible", Os.WINDOWS, _cmd(ps(usb.PS_VCP_STATUS), "Error\n")),
    ("USB-050", "not-in-group", Os.MACOS, _no_group),
    ("USB-060", "held-by-sadi", Os.LINUX, _cmd("-F pc /dev/ttyUSB0", "p10\ncsadi\n")),
    ("USB-060", "held-by-labview", Os.WINDOWS, _cmd(ps(usb.PS_HOLDERS), "LabVIEW\n")),
    (
        "USB-060",
        "held-by-other",
        Os.MACOS,
        _cmd("-F pc /dev/cu.usbserial-FT1", "p77\ncscreen\n"),
    ),
    ("USB-060", "modemmanager-probing", Os.LINUX, _cmd("is-active ModemManager", "active\n")),
    (
        "USB-070",
        "latency-not-2ms",
        Os.LINUX,
        _set_file("/sys/bus/usb-serial/devices/ttyUSB0/latency_timer", "16\n"),
    ),
    ("USB-080", "vhci-missing", Os.WSL, _wsl_attached("CONFIG_USB_SERIAL_FTDI_SIO=y\n")),
    (
        "USB-080",
        "attach-dropped",
        Os.WSL,
        _wsl_attached(_KCONF_OK, "vhci_hcd vhci_hcd.0: connection error\n"),
    ),
    ("USB-080", "attached-no-node", Os.WSL, _all(_wsl_attached(_KCONF_OK), _no_node)),
    ("CLK-010", "clock-before-build", Os.LINUX, _set(clock=1_000_000.0)),
    ("RES-010", "single-core", Os.LINUX, _set(cpus=1)),
    ("RES-020", "low-memory", Os.LINUX, _set(mem=700 * 1024**2)),
    ("RES-020", "very-low-memory", Os.WINDOWS, _set(mem=100 * 1024**2)),
    ("RES-030", "low-nofile", Os.MACOS, _set(nofile=256)),
    ("BRW-010", "no-browser", Os.LINUX, _set(browser=False)),
    ("BRW-010", "wsl-no-wslview", Os.WSL, _set(browser=False)),
    (
        "PLG-010",
        "plugin-error",
        Os.LINUX,
        _set(
            findings=[
                DoctorFinding(
                    plugin_id="p",
                    severity=FSev.ERROR,
                    code="plugin.import_failed",
                    message="bad",
                    fixes=("1. Reinstall p",),
                )
            ]
        ),
    ),
    (
        "PLG-010",
        "plugin-warning",
        Os.LINUX,
        _set(
            findings=[
                DoctorFinding(
                    plugin_id="p", severity=FSev.WARNING, code="w", message="meh", fixes=()
                )
            ]
        ),
    ),
    ("SESS-010", "foreign-dir", Os.LINUX, _sess(_sf(name="notes", name_ok=False))),
    ("SESS-010", "incomplete", Os.LINUX, _sess(_sf(has_wal=False, segments=0, wal="none"))),
    ("SESS-010", "manifest-unparseable", Os.LINUX, _sess(_sf(manifest="unparseable"))),
    ("SESS-010", "manifest-stale", Os.WINDOWS, _sess(_sf(manifest="missing", manifest_stale=True))),
    (
        "SESS-020",
        "locked-live",
        Os.LINUX,
        _sess(_sf(state="open", lock_holder="pid=1", holder_alive=True)),
    ),
    (
        "SESS-020",
        "locked-dead-pid-reused",
        Os.MACOS,
        _sess(_sf(lock_holder="pid=1", holder_alive=False, pid_reused=True)),
    ),
    (
        "SESS-020",
        "crashed",
        Os.WSL,
        _sess(_sf(state="open", lock_holder="pid=1", holder_alive=False)),
    ),
    (
        "SESS-020",
        "lock-on-network-fs",
        Os.LINUX,
        lambda p: (_sess(_sf(lock_holder="pid=1"))(p), setattr(p, "fs", "nfs"))[0],
    ),
    ("SESS-030", "tmp-leftovers", Os.LINUX, _sess(_sf(tmp_files=("x.tmp",)))),
    ("SESS-030", "export-without-sidecar", Os.LINUX, _sess(_sf(orphan_exports=("a.csv",)))),
    (
        "SESS-040",
        "version-gap",
        Os.LINUX,
        _sess(_sf(name="20261108T153000Z-demo.v003", version=3)),
    ),
    ("SESS-040", "parent-missing", Os.LINUX, _sess(_sf(parent="gone.v001"))),
    (
        "SESS-040",
        "parent-mismatch",
        Os.LINUX,
        _sess(
            _sf(),
            _sf(
                name="20261108T153000Z-demo.v002",
                version=2,
                parent="20261108T153000Z-demo.v001",
                parent_last_seq=9,
            ),
        ),
    ),
    ("SESS-050", "not-owned-by-user", Os.LINUX, _sess(_sf(not_owned=True))),
    ("SESS-050", "read-only-session", Os.LINUX, _sess(_sf(read_only=True))),
    ("WAL-010", "torn-tail", Os.LINUX, _sess(_sf(wal="torn-tail", tail_bytes=7))),
    ("WAL-010", "corrupt", Os.LINUX, _sess(_sf(wal="corrupt", wal_detail="bad crc"))),
    ("WAL-010", "unsupported-format", Os.LINUX, _sess(_sf(wal="unsupported-format"))),
    ("WAL-010", "header-invalid", Os.LINUX, _sess(_sf(wal="header-invalid"))),
    ("WAL-020", "torn-tail", Os.LINUX, _sess(_sf(wal="torn-tail"))),
    ("WAL-020", "corrupt", Os.LINUX, _sess(_sf(wal="corrupt"))),
    ("WAL-020", "unsupported-format", Os.LINUX, _sess(_sf(wal="unsupported-format"))),
    ("WAL-020", "header-invalid", Os.LINUX, _sess(_sf(wal="header-invalid"))),
    ("WAL-020", "seal-mismatch", Os.LINUX, _sess(_sf(wal="seal-mismatch"))),
    ("WAL-020", "seq-gap", Os.LINUX, _sess(_sf(wal="seq-gap"))),
    ("WAL-020", "deep-timeout", Os.LINUX, _sess(_sf(wal="timeout"))),
    ("WAL-030", "stale-snapshots", Os.LINUX, _sess(_sf(snapshots_stale=1))),
    ("WAL-030", "invalid-snapshot", Os.LINUX, _sess(_sf(snapshots_invalid=1))),
    ("WAL-040", "undecodable-version", Os.LINUX, _sess(_sf(raw_before_settings=True))),
    ("DEV-010", "open-denied", Os.LINUX, _dev(open_status="denied")),
    ("DEV-010", "open-busy", Os.MACOS, _dev(open_status="busy")),
    ("DEV-010", "open-io-error", Os.WINDOWS, _dev(open_status="io-error")),
    ("DEV-020", "no-reply", Os.WSL, _dev(query_status="no-reply")),
    ("DEV-020", "garbage-reply", Os.LINUX, _dev(query_status="garbage", reply_hex="ff00")),
    ("DEV-020", "unexpected-firmware", Os.LINUX, _dev(fw_version="9.9")),
    ("DEV-030", "streaming-unattended", Os.LINUX, _dev(state="running", state_byte=3)),
    ("DEV-030", "unknown-state", Os.LINUX, _dev(state="unknown", state_byte=9)),
    ("DEV-040", "low-rate", Os.LINUX, _dev(packets_per_s=300.0)),
    ("DEV-040", "gaps", Os.LINUX, _dev(gap_events=2)),
    ("DEV-040", "saturated-channel", Os.LINUX, _dev(saturated_channels=(1,))),
    ("DEV-040", "stop-not-acked", Os.LINUX, _dev(stop_acked=False)),
    ("DEV-050", "boot-timeout", Os.LINUX, _dev(boot_status="timeout", boot_seconds=10.0)),
    ("DEV-050", "boot-slow", Os.LINUX, _dev(boot_seconds=5.0)),
    ("SIM-010", "sim-connect-fail", Os.LINUX, _simf(connect_ok=False)),
    ("SIM-010", "sim-data-mismatch", Os.LINUX, _simf(data_ok=False)),
    ("SIM-010", "sim-timeout", Os.LINUX, _simf(timed_out=True)),
    ("SIM-020", "scenario-load-fail", Os.LINUX, _simf(failed_scenarios=("noisy",))),
    ("WRK-010", "spawn-fail", Os.WINDOWS, _wrk(spawn_status="fail")),
    ("WRK-010", "spawn-slow", Os.WINDOWS, _wrk(spawn_seconds=12.0)),
    ("WRK-010", "child-imports-store", Os.LINUX, _wrk(imports_store=True)),
    ("WRK-020", "orphan-survives", Os.LINUX, _wrk(orphan_survives=True)),
]


def _run(p: FakeProbes, os: Os, **opts: object) -> DoctorReport:
    options = RunOptions.model_validate({"render_os": os, **opts})
    return doctor.run(options, p).unwrap()


def test_healthy_machine_is_ready() -> None:
    """A healthy fake machine passes everything and exits 0."""
    report = _run(healthy(), Os.LINUX, data_root=ROOT)
    bad = [r.id for r in report.results if r.status in (Status.FAIL, Status.WARN)]
    assert bad == []
    assert report.summary.verdict == "ready"
    assert doctor.exit_code(report) == 0


# frob:tests python/sadi/doctor/__init__.py::exit_code
# frob:tests python/sadi/doctor/__init__.py::run
# frob:tests python/sadi/doctor/__init__.py::summarize
# frob:tests python/sadi/doctor/checks/brw.py::brw_010
# frob:tests python/sadi/doctor/checks/brw.py::brw_020
# frob:tests python/sadi/doctor/checks/brw.py::brw_030
# frob:tests python/sadi/doctor/checks/clk.py::clk_010
# frob:tests python/sadi/doctor/checks/ext.py::ext_020
# frob:tests python/sadi/doctor/checks/ext.py::ext_030
# frob:tests python/sadi/doctor/checks/ext.py::ext_040
# frob:tests python/sadi/doctor/checks/ext.py::ext_050
# frob:tests python/sadi/doctor/checks/ext.py::child_json
# frob:tests python/sadi/doctor/checks/usb.py::serial_nodes
# frob:tests python/sadi/doctor/checks/usb.py::ftdi_devices
# frob:tests python/sadi/doctor/checks/usb.py::usb_010
# frob:tests python/sadi/doctor/checks/usb.py::usb_060
# frob:tests python/sadi/doctor/checks/usb.py::usb_070
# frob:tests python/sadi/doctor/checks/usb.py::usb_080
# frob:tests python/sadi/doctor/checks/net.py::net_030
# frob:tests python/sadi/doctor/checks/net.py::net_040
# frob:tests python/sadi/doctor/checks/net.py::health_script
# frob:tests python/sadi/doctor/checks/py.py::py_050
# frob:tests python/sadi/doctor/checks/py.py::py_060
# frob:tests python/sadi/doctor/checks/sess.py::sess_010
# frob:tests python/sadi/doctor/checks/sess.py::sess_020
# frob:tests python/sadi/doctor/checks/sess.py::sess_030
# frob:tests python/sadi/doctor/checks/sess.py::sess_040
# frob:tests python/sadi/doctor/checks/sess.py::sess_050
# frob:tests python/sadi/doctor/checks/wal.py::wal_010
# frob:tests python/sadi/doctor/checks/wal.py::wal_020
# frob:tests python/sadi/doctor/checks/wal.py::wal_030
# frob:tests python/sadi/doctor/checks/wal.py::wal_040
# frob:tests python/sadi/doctor/probes.py::Probes.session_facts
# frob:tests python/sadi/doctor/probes.py::RealProbes.session_facts
# frob:tests python/sadi/doctor/checks/data.py::data_040
# frob:tests python/sadi/doctor/checks/data.py::data_050
# frob:tests python/sadi/doctor/checks/data.py::data_060
# frob:tests python/sadi/doctor/checks/data.py::data_070
# frob:tests python/sadi/doctor/checks/data.py::data_080
# frob:tests python/sadi/doctor/checks/clk.py::clk_020
# frob:tests python/sadi/doctor/checks/clk.py::clk_030
# frob:tests python/sadi/doctor/checks/clk.py::clk_040
# frob:tests python/sadi/doctor/checks/res.py::res_040
# frob:tests python/sadi/doctor/checks/data.py::data_010
# frob:tests python/sadi/doctor/checks/data.py::data_020
# frob:tests python/sadi/doctor/checks/data.py::data_030
# frob:tests python/sadi/doctor/checks/data.py::data_090
# frob:tests python/sadi/doctor/checks/dev.py::dev_010
# frob:tests python/sadi/doctor/checks/dev.py::dev_020
# frob:tests python/sadi/doctor/checks/dev.py::dev_030
# frob:tests python/sadi/doctor/checks/dev.py::dev_040
# frob:tests python/sadi/doctor/checks/dev.py::dev_050
# frob:tests python/sadi/doctor/checks/sim.py::sim_010
# frob:tests python/sadi/doctor/checks/sim.py::sim_020
# frob:tests python/sadi/doctor/checks/wrk.py::wrk_010
# frob:tests python/sadi/doctor/checks/wrk.py::wrk_020
# frob:tests python/sadi/doctor/checks/ext.py::ext_010
# frob:tests python/sadi/doctor/checks/net.py::net_010
# frob:tests python/sadi/doctor/checks/net.py::net_020
# frob:tests python/sadi/doctor/checks/plat.py::plat_010
# frob:tests python/sadi/doctor/checks/plat.py::plat_020
# frob:tests python/sadi/doctor/checks/plat.py::plat_040
# frob:tests python/sadi/doctor/checks/plat.py::plat_030
# frob:tests python/sadi/doctor/checks/plat.py::plat_050
# frob:tests python/sadi/doctor/checks/plg.py::plg_010
# frob:tests python/sadi/doctor/checks/py.py::py_010
# frob:tests python/sadi/doctor/checks/py.py::py_020
# frob:tests python/sadi/doctor/checks/py.py::py_030
# frob:tests python/sadi/doctor/checks/py.py::py_040
# frob:tests python/sadi/doctor/checks/res.py::res_010
# frob:tests python/sadi/doctor/checks/res.py::res_020
# frob:tests python/sadi/doctor/checks/res.py::res_030
# frob:tests python/sadi/doctor/checks/res.py::worker_count
# frob:tests python/sadi/doctor/checks/usb.py::ftdi_sysfs
# frob:tests python/sadi/doctor/checks/usb.py::usb_020
# frob:tests python/sadi/doctor/checks/usb.py::usb_030
# frob:tests python/sadi/doctor/checks/usb.py::usb_040
# frob:tests python/sadi/doctor/checks/usb.py::usb_050
# frob:tests python/sadi/doctor/checks/usb.py::usbipd_ftdi
# frob:tests python/sadi/doctor/checks/web.py::web_010
# frob:tests python/sadi/doctor/checks/web.py::web_020
# frob:tests python/sadi/doctor/cli.py::main
# frob:tests python/sadi/doctor/registry.py::all_checks
# frob:tests python/sadi/doctor/registry.py::check
# frob:tests python/sadi/doctor/registry.py::fail
# frob:tests python/sadi/doctor/registry.py::ok
# frob:tests python/sadi/doctor/registry.py::remedy
# frob:tests python/sadi/doctor/registry.py::skip
# frob:tests python/sadi/doctor/registry.py::warn
# frob:tests python/sadi/doctor/render_text.py::render
# frob:tests python/sadi/doctor/steps.py::action
# frob:tests python/sadi/doctor/steps.py::cmd
# frob:tests python/sadi/doctor/steps.py::manual
# frob:tests python/sadi/doctor/steps.py::shell_for
# frob:tests python/sadi/doctor/steps.py::verify
@pytest.mark.parametrize(
    ("check_id", "mode", "os", "mutate"), CASES, ids=[f"{c}-{m}" for c, m, _, _ in CASES]
)
def test_fault_injection_yields_mode_and_remedy(
    check_id: str, mode: str, os: Os, mutate: Mut
) -> None:
    """Breaking one fact produces exactly that mode with a numbered, verified remediation."""
    p = healthy()
    p.os = os
    mutate(p)
    port = 80 if mode == "port-privileged" else 8000
    report = _run(
        p,
        os,
        data_root=_ROOT_FOR.get((check_id, mode), ROOT),
        allow_network_fs=False,
        api_port=port,
        open_browser=check_id == "BRW-030",
        deep=check_id == "WAL-020",
        stream_seconds=5 if check_id == "DEV-040" else 0,
        with_reset=check_id == "DEV-050",
        running=check_id == "NET-040",
        allow_probe_write=check_id == "DATA-040",
    )
    result = next(r for r in report.results if r.id == check_id)
    assert result.mode == mode, result.headline
    assert result.status in (Status.WARN, Status.FAIL)
    rem = result.remediation
    assert rem is not None and rem.os is os
    assert rem.steps[-1].kind is StepKind.VERIFY
    assert f"--check {check_id}" in rem.steps[-1].commands[0].line
    assert all(s.expect for s in rem.steps)
    text = render(report)
    assert f"{check_id}" in text and "Expect:" in text
    assert text.isascii()


def test_declared_modes_are_all_injected() -> None:
    """Every failure mode the catalog declares has a fault-injection case (no dead modes)."""
    declared = {(s.id, m) for s, _ in all_checks() for m in s.modes}
    covered = {(c, m) for c, m, _, _ in CASES}
    assert declared - covered == set()
    assert covered - declared == set()


def test_every_mode_has_a_remedy_for_every_os() -> None:
    """Remedies build for all four OSes and honour the schema invariants."""
    from sadi.doctor.registry import Ctx, Outcome

    for spec, _ in all_checks():
        for mode in spec.modes:
            fn = get_remedy(spec.id, mode)
            assert fn is not None, f"{spec.id}/{mode}"
            for os in Os:
                ctx = Ctx(probes=healthy(), options=RunOptions(), os=os, data_root=ROOT)
                fix = fn(ctx, Outcome(Status.FAIL, "x", mode=mode))
                assert fix.steps, f"{spec.id}/{mode}/{os}"
                for s in fix.steps:
                    assert s.kind is not StepKind.VERIFY
                    if s.mutates is Mutates.DATA:
                        assert not s.commands


def test_prerequisite_failure_skips_dependants() -> None:
    """A failed dependency skips dependants with a reason rather than running them."""
    p = healthy()
    _no_usb(p)
    report = _run(p, Os.LINUX, data_root=ROOT)
    skipped = {r.id: r for r in report.results if r.status is Status.SKIP}
    assert skipped["USB-030"].skip_reason is SkipReason.PREREQUISITE_FAILED
    assert "USB-050" in skipped


def test_crashing_check_becomes_probe_error() -> None:
    """An exception inside a probe is reported as a probe-error fail, not a doctor crash."""
    p = healthy()

    def boom() -> tuple[bool, int]:
        raise RuntimeError("kaput")

    p.web_bundle = boom  # type: ignore[method-assign]
    report = _run(p, Os.LINUX, data_root=ROOT)
    r = next(r for r in report.results if r.id == "WEB-010")
    assert r.status is Status.FAIL and r.mode == "probe-error"
    assert r.evidence.error is not None and "kaput" in r.evidence.error.detail
    assert r.remediation is not None


def test_selection_and_unknown_ids() -> None:
    """--check/--layer/--skip filter; an unknown id is a DoctorError."""
    p = healthy()
    only = _run(p, Os.LINUX, checks=("PY-010",), data_root=ROOT)
    assert [r.id for r in only.results] == ["PY-010"]
    layer = _run(p, Os.LINUX, layers=(Layer.CLK,), data_root=ROOT)
    assert {r.layer for r in layer.results} == {Layer.CLK}
    skipped = _run(p, Os.LINUX, skip=("PY-010",), data_root=ROOT)
    assert "PY-010" not in {r.id for r in skipped.results}
    assert doctor.run(RunOptions(checks=("ZZZ-999",)), p).is_err


def test_exit_codes_and_verdict() -> None:
    """Blocker fail is 2, other fail is 1, warnings-only is 0."""
    p = healthy()
    p.browser = False
    assert doctor.exit_code(_run(p, Os.LINUX, data_root=ROOT)) == 0
    p = healthy()
    _no_usb(p)
    r = _run(p, Os.LINUX, data_root=ROOT)
    assert doctor.exit_code(r) == 1 and r.summary.verdict == "degraded"
    p = healthy()
    p.py = (3, 9, 0)
    r = _run(p, Os.LINUX, data_root=ROOT)
    assert doctor.exit_code(r) == 2 and r.summary.verdict == "blocked"
    assert r.summary.first_action is not None
    assert r.summary.first_action


def test_json_round_trip() -> None:
    """The report serialises to JSON and validates back unchanged."""
    p = healthy()
    _no_usb(p)
    report = _run(p, Os.LINUX, data_root=ROOT)
    again = DoctorReport.model_validate_json(report.model_dump_json())
    assert again == report
    assert json.loads(report.model_dump_json())["schema_version"] == 1


def test_data_root_resolution() -> None:
    """--data-root beats SADI_DATA_ROOT beats the per-user default."""
    p = healthy()
    assert doctor.resolve_data_root(RunOptions(), p) == p.data_dir
    p.environ["SADI_DATA_ROOT"] = "/env"
    assert doctor.resolve_data_root(RunOptions(), p) == "/env"
    assert doctor.resolve_data_root(RunOptions(data_root="/flag"), p) == "/flag"


def test_cli_list_explain_and_usage(capsys: pytest.CaptureFixture[str]) -> None:
    """The CLI lists checks, explains one, and rejects unknown ids with 64."""
    assert cli.main(["list"]) == 0
    assert "USB-020" in capsys.readouterr().out
    assert cli.main(["explain", "USB-020"]) == 0
    assert "no-device" in capsys.readouterr().out
    assert cli.main(["explain", "NOPE-1"]) == 64
    assert cli.main(["--check", "ZZZ-999"]) == 64
    assert cli.main(["--bogus"]) == 64


def test_cli_json_on_real_machine(capsys: pytest.CaptureFixture[str]) -> None:
    """A real run emits a valid JSON report and an exit code in {0,1,2}."""
    code = cli.main(["--json", "--check", "CLK-010", "--check", "PY-010"])
    out = capsys.readouterr().out
    assert code in (0, 1, 2)
    assert DoctorReport.model_validate_json(out).results


def test_severity_enum_has_blocker() -> None:
    """Guard: exit-code mapping relies on the BLOCKER severity name."""
    assert Severity.BLOCKER.value == "blocker"


def test_doctor_is_read_only() -> None:
    """No doctor source writes files, spawns shells, or mutates the system."""
    banned = re.compile(
        r"\.write_text\(|\.write_bytes\(|os\.remove|os\.unlink|shutil\.|\bmkdir\(|makedirs|"
        r"shell=True|os\.system|\bchmod\(|\.touch\(|open\([^)]*['\"][wax+]"
    )
    src = Path(doctor.__file__).parent
    hits = [
        f"{p.name}:{i}"
        for p in src.rglob("*.py")
        for i, line in enumerate(p.read_text().splitlines(), 1)
        if banned.search(line)
        and "disk_usage" not in line
        and "shutil.which" not in line
        and "import shutil" not in line
        and "chmod 660" not in line
        and p.name != "volprobe.py"  # opt-in flush probe: one file under <root>/doctor/
        and p.name != "bundle.py"  # the only writer: new path, no-replace, outside the data root
    ]
    assert hits == []


def test_catalog_docs_are_current() -> None:
    """docs/doctor-checks.md matches `sadi-doctor docs` output."""
    doc = Path(__file__).resolve().parents[3] / "docs" / "doctor-checks.md"
    assert (
        doc.read_text() == cli.catalog_markdown() + "\n"
        or doc.read_text() == cli.catalog_markdown()
    )


# frob:tests python/sadi/doctor/probes.py::Probes.bind_state
# frob:tests python/sadi/doctor/probes.py::Probes.browser_available
# frob:tests python/sadi/doctor/probes.py::Probes.cpu_count
# frob:tests python/sadi/doctor/probes.py::Probes.disk_free
# frob:tests python/sadi/doctor/probes.py::Probes.dist_version
# frob:tests python/sadi/doctor/probes.py::Probes.encoding
# frob:tests python/sadi/doctor/probes.py::Probes.env
# frob:tests python/sadi/doctor/probes.py::Probes.exists
# frob:tests python/sadi/doctor/probes.py::Probes.fstype
# frob:tests python/sadi/doctor/probes.py::Probes.import_error
# frob:tests python/sadi/doctor/probes.py::Probes.is_dir
# frob:tests python/sadi/doctor/probes.py::Probes.listdir
# frob:tests python/sadi/doctor/probes.py::Probes.localhost_addrs
# frob:tests python/sadi/doctor/probes.py::Probes.loopback_ok
# frob:tests python/sadi/doctor/probes.py::Probes.machine
# frob:tests python/sadi/doctor/probes.py::Probes.mem_available
# frob:tests python/sadi/doctor/probes.py::Probes.node_access
# frob:tests python/sadi/doctor/probes.py::Probes.nofile_soft
# frob:tests python/sadi/doctor/probes.py::Probes.now
# frob:tests python/sadi/doctor/probes.py::Probes.os_kind
# frob:tests python/sadi/doctor/probes.py::Probes.os_version
# frob:tests python/sadi/doctor/probes.py::Probes.plugin_findings
# frob:tests python/sadi/doctor/probes.py::Probes.py_version
# frob:tests python/sadi/doctor/probes.py::Probes.python_exe
# frob:tests python/sadi/doctor/probes.py::Probes.read_text
# frob:tests python/sadi/doctor/probes.py::Probes.readlink
# frob:tests python/sadi/doctor/probes.py::Probes.requires_python
# frob:tests python/sadi/doctor/probes.py::Probes.run
# frob:tests python/sadi/doctor/probes.py::Probes.spill_files
# frob:tests python/sadi/doctor/probes.py::Probes.user_data_dir
# frob:tests python/sadi/doctor/probes.py::Probes.user_groups
# frob:tests python/sadi/doctor/probes.py::Probes.web_bundle
# frob:tests python/sadi/doctor/probes.py::Probes.which
# frob:tests python/sadi/doctor/probes.py::Probes.writable
# frob:tests python/sadi/doctor/probes.py::RealProbes.bind_state
# frob:tests python/sadi/doctor/probes.py::RealProbes.browser_available
# frob:tests python/sadi/doctor/probes.py::RealProbes.cpu_count
# frob:tests python/sadi/doctor/probes.py::RealProbes.disk_free
# frob:tests python/sadi/doctor/probes.py::RealProbes.dist_version
# frob:tests python/sadi/doctor/probes.py::RealProbes.encoding
# frob:tests python/sadi/doctor/probes.py::RealProbes.env
# frob:tests python/sadi/doctor/probes.py::RealProbes.exists
# frob:tests python/sadi/doctor/probes.py::RealProbes.fstype
# frob:tests python/sadi/doctor/probes.py::RealProbes.import_error
# frob:tests python/sadi/doctor/probes.py::RealProbes.is_dir
# frob:tests python/sadi/doctor/probes.py::RealProbes.listdir
# frob:tests python/sadi/doctor/probes.py::RealProbes.localhost_addrs
# frob:tests python/sadi/doctor/probes.py::RealProbes.loopback_ok
# frob:tests python/sadi/doctor/probes.py::RealProbes.machine
# frob:tests python/sadi/doctor/probes.py::RealProbes.mem_available
# frob:tests python/sadi/doctor/probes.py::RealProbes.node_access
# frob:tests python/sadi/doctor/probes.py::RealProbes.nofile_soft
# frob:tests python/sadi/doctor/probes.py::RealProbes.now
# frob:tests python/sadi/doctor/probes.py::RealProbes.os_kind
# frob:tests python/sadi/doctor/probes.py::RealProbes.os_version
# frob:tests python/sadi/doctor/probes.py::RealProbes.plugin_findings
# frob:tests python/sadi/doctor/probes.py::RealProbes.py_version
# frob:tests python/sadi/doctor/probes.py::RealProbes.python_exe
# frob:tests python/sadi/doctor/probes.py::RealProbes.read_text
# frob:tests python/sadi/doctor/probes.py::RealProbes.readlink
# frob:tests python/sadi/doctor/probes.py::RealProbes.requires_python
# frob:tests python/sadi/doctor/probes.py::RealProbes.run
# frob:tests python/sadi/doctor/probes.py::RealProbes.spill_files
# frob:tests python/sadi/doctor/probes.py::RealProbes.user_data_dir
# frob:tests python/sadi/doctor/probes.py::RealProbes.user_groups
# frob:tests python/sadi/doctor/probes.py::RealProbes.web_bundle
# frob:tests python/sadi/doctor/probes.py::RealProbes.which
# frob:tests python/sadi/doctor/probes.py::RealProbes.writable
def test_real_probes_full_run_is_valid() -> None:
    """Every check runs against the real machine without crashing and yields a valid report."""
    report = doctor.run(RunOptions()).unwrap()
    assert len(report.results) == len(list(all_checks()))
    assert DoctorReport.model_validate_json(report.model_dump_json()) == report
    assert doctor.exit_code(report) in (0, 1, 2)


# frob:tests python/sadi/doctor/checks/dev.py::dev_010
# frob:tests python/sadi/doctor/checks/dev.py::dev_020
# frob:tests python/sadi/doctor/checks/dev.py::dev_030
def test_no_device_is_informational_skip() -> None:
    """With no board attached every DEV check skips with no-device instead of failing."""
    p = healthy()
    p.device = DeviceFacts()
    report = _run(p, Os.LINUX, data_root=ROOT, stream_seconds=5, with_reset=True)
    dev = [r for r in report.results if r.id.startswith("DEV-")]
    assert len(dev) == 5
    assert all(r.status is Status.SKIP and r.skip_reason is SkipReason.NO_DEVICE for r in dev)
    assert report.summary.verdict == "ready"


# frob:tests python/sadi/doctor/checks/dev.py::device
# frob:tests python/sadi/doctor/checks/dev.py::dev_040
# frob:tests python/sadi/doctor/checks/dev.py::dev_050
def test_stream_and_reset_checks_are_opt_in() -> None:
    """DEV-040 and DEV-050 only run with --stream-seconds / --with-reset."""
    off = {r.id: r for r in _run(healthy(), Os.LINUX, data_root=ROOT).results}
    assert off["DEV-040"].status is Status.SKIP and off["DEV-050"].status is Status.SKIP
    on = {
        r.id: r
        for r in _run(
            healthy(), Os.LINUX, data_root=ROOT, stream_seconds=5, with_reset=True
        ).results
    }
    assert on["DEV-040"].status is Status.PASS and on["DEV-050"].status is Status.PASS


# frob:tests python/sadi/doctor/checks/sim.py::sim_010
# frob:tests python/sadi/doctor/checks/sim.py::sim_020
def test_missing_binding_skips_sim_checks() -> None:
    """Without the native binding the simulator checks skip rather than fail."""
    p = healthy()
    p.sim = SimFacts(binding_ok=False, detail="no module")
    got = {r.id: r for r in _run(p, Os.LINUX, data_root=ROOT).results}
    assert got["SIM-010"].status is Status.SKIP and got["SIM-020"].status is Status.SKIP


# frob:tests python/sadi/doctor/probes.py::RealProbes.__init__
# frob:tests python/sadi/doctor/probes.py::Probes.device_facts
# frob:tests python/sadi/doctor/probes.py::Probes.sim_facts
# frob:tests python/sadi/doctor/probes.py::Probes.worker_facts
# frob:tests python/sadi/doctor/workerprobe.py::selftest
# frob:tests python/sadi/doctor/workerprobe.py::watchdog
# frob:tests python/sadi/doctor/workerprobe.py::probe_workers
# frob:tests python/sadi/doctor/devprobe.py::probe_device
# frob:tests python/sadi/doctor/devprobe.py::probe_sim
# frob:tests python/sadi/doctor/probes.py::RealProbes.worker_facts
# frob:tests python/sadi/doctor/probes.py::RealProbes.device_facts
# frob:tests python/sadi/doctor/probes.py::RealProbes.sim_facts
def test_real_probes_degrade_and_workers_stay_clean() -> None:
    """Real probes never crash; workers do not import the store; no board is no-device."""
    from sadi.doctor.probes import RealProbes

    rp = RealProbes()
    w = rp.worker_facts()
    assert w.spawn_status == "ok" and not w.imports_store and not w.orphan_survives
    d = rp.device_facts(None, 0, False)
    assert d.open_status in ("no-device", "ok", "denied", "busy", "io-error")
    assert isinstance(rp.sim_facts().binding_ok, bool)


# frob:tests python/sadi/doctor/checks/dev.py::dev_010
# frob:tests python/sadi/doctor/checks/dev.py::dev_020
# frob:tests python/sadi/doctor/checks/dev.py::dev_030
# frob:tests python/sadi/doctor/checks/dev.py::dev_040
# frob:tests python/sadi/doctor/checks/dev.py::dev_050
# frob:tests python/sadi/doctor/checks/sim.py::sim_010
# frob:tests python/sadi/doctor/checks/sim.py::sim_020
# frob:tests python/sadi/doctor/checks/wrk.py::wrk_010
# frob:tests python/sadi/doctor/checks/wrk.py::wrk_020
def test_dev_sim_wrk_modes_yield_remedies_on_their_os() -> None:
    """Each DEV, SIM and WRK mode is reachable and carries a verified remedy."""
    cases = [c for c in CASES if c[0].split("-")[0] in ("DEV", "SIM", "WRK")]
    assert len(cases) == 22
    for check_id, mode, os, mutate in cases:
        p = healthy()
        p.os = os
        mutate(p)
        report = _run(p, os, data_root=ROOT, stream_seconds=5, with_reset=True)
        result = next(r for r in report.results if r.id == check_id)
        assert result.mode == mode, (check_id, result.headline)
        rem = result.remediation
        assert rem is not None and rem.steps[-1].kind is StepKind.VERIFY
        assert render(report).isascii()


# frob:tests python/sadi/doctor/probes.py::Probes.package_integrity
# frob:tests python/sadi/doctor/probes.py::RealProbes.package_integrity
def test_real_package_integrity_returns_two_lists() -> None:
    """The real integrity probe is read-only and yields (modified, missing) lists."""
    from sadi.doctor.probes import RealProbes

    modified, missing = RealProbes().package_integrity()
    assert isinstance(modified, list) and isinstance(missing, list)


# frob:tests python/sadi/doctor/volprobe.py::probe_flush
# frob:tests python/sadi/doctor/volprobe.py::probe_lock
def test_real_volume_probes_flush_lock_and_clean_up(tmp_path: Path) -> None:
    """The real flush probe leaves nothing behind and the lock probe reports ok."""
    from sadi.doctor.volprobe import probe_flush, probe_lock

    facts = probe_flush(str(tmp_path))
    assert facts.status == "ok" and facts.p50_ms >= 0
    assert list((tmp_path / "doctor").iterdir()) == []
    target = tmp_path / "config.toml"
    target.write_text("")
    assert probe_lock(str(target)) == "ok"
    assert probe_lock(str(tmp_path / "missing")) == "error"


def test_data_040_is_skipped_without_the_opt_in() -> None:
    """DATA-040 writes, so it is skipped unless --allow-probe-write is given."""
    report = _run(healthy(), Os.LINUX, data_root=ROOT)
    r = next(x for x in report.results if x.id == "DATA-040")
    assert r.status is Status.SKIP and r.skip_reason is SkipReason.OPT_IN


# frob:tests python/sadi/doctor/probes.py::Probes.flush_facts
# frob:tests python/sadi/doctor/probes.py::Probes.lock_state
# frob:tests python/sadi/doctor/probes.py::Probes.file_size
# frob:tests python/sadi/doctor/probes.py::Probes.on_battery
# frob:tests python/sadi/doctor/probes.py::Probes.monotonic_resolution
# frob:tests python/sadi/doctor/probes.py::Probes.tz_name
# frob:tests python/sadi/doctor/probes.py::RealProbes.flush_facts
# frob:tests python/sadi/doctor/probes.py::RealProbes.lock_state
# frob:tests python/sadi/doctor/probes.py::RealProbes.file_size
# frob:tests python/sadi/doctor/probes.py::RealProbes.on_battery
# frob:tests python/sadi/doctor/probes.py::RealProbes.monotonic_resolution
# frob:tests python/sadi/doctor/probes.py::RealProbes.tz_name
def test_real_probes_answer_the_new_facts(tmp_path: Path) -> None:
    """The real probes return well-typed answers for the clock, power, size, lock and flush facts."""
    from sadi.doctor.probes import RealProbes

    rp = RealProbes()
    f = tmp_path / "a.log"
    f.write_text("abc")
    assert rp.file_size(str(f)) == 3 and rp.file_size(str(tmp_path / "none")) is None
    assert rp.lock_state(str(f)) == "ok"
    assert rp.flush_facts(str(tmp_path)).status == "ok"
    assert rp.monotonic_resolution() > 0
    assert rp.on_battery() in (True, False, None)
    assert rp.tz_name() is None or isinstance(rp.tz_name(), str)


# frob:tests python/sadi/doctor/hostprobe.py::mount_fstype
def test_mount_fstype_picks_longest_prefix() -> None:
    """macOS `mount` output resolves to the deepest containing mount's fstype."""
    out = (
        "/dev/disk3s1 on / (apfs, local, journaled)\n"
        "//u@nas/share on /Volumes/share (smbfs, nodev, nosuid)\n"
    )
    assert hostprobe.mount_fstype(out, "/Volumes/share/x") == "smbfs"
    assert hostprobe.mount_fstype(out, "/Users/u") == "apfs"
    assert hostprobe.mount_fstype("garbage", "/x") is None


# frob:tests python/sadi/doctor/hostprobe.py::family_of
# frob:tests python/sadi/doctor/hostprobe.py::major_version
def test_browser_parsers() -> None:
    """Browser names and version strings parse to a family and a major number."""
    assert hostprobe.family_of("ChromeHTML") == "chromium"
    assert hostprobe.family_of("FirefoxURL-308046B0AF4A39CB") == "firefox"
    assert hostprobe.family_of("Opera") is None
    assert hostprobe.major_version("Mozilla Firefox 115.2.1") == 115
    assert hostprobe.major_version("none") is None


# frob:tests python/sadi/doctor/checks/data.py::data_020
@pytest.mark.parametrize("os", [Os.WINDOWS, Os.MACOS])
def test_data_020_probes_windows_and_macos(os: Os) -> None:
    """DATA-020 no longer skips Windows or macOS; a network fstype is flagged there."""
    p = healthy()
    p.os = os
    p.fs = "smbfs"
    report = _run(p, os, data_root=ROOT, allow_network_fs=False)
    result = next(r for r in report.results if r.id == "DATA-020")
    assert result.status is Status.FAIL or result.status is Status.WARN
    p.fs = "ntfs" if os is Os.WINDOWS else "apfs"
    report = _run(p, os, data_root=ROOT, allow_network_fs=False)
    assert next(r for r in report.results if r.id == "DATA-020").status is Status.PASS


# frob:tests python/sadi/doctor/checks/plat.py::plat_020
def test_plat_020_skips_without_build_target() -> None:
    """Without BUILD_TARGET the architecture check is UNVERIFIED, never a false pass."""
    p = healthy()
    p.target = None
    report = _run(p, Os.LINUX, data_root=ROOT)
    result = next(r for r in report.results if r.id == "PLAT-020")
    assert result.status is Status.SKIP and result.skip_reason is SkipReason.UNVERIFIED


# frob:tests python/sadi/doctor/checks/web.py::web_020
def test_web_020_skips_without_version_json() -> None:
    """A bundle without version.json is UNVERIFIED."""
    p = healthy()
    p.web_ver = None
    report = _run(p, Os.LINUX, data_root=ROOT)
    result = next(r for r in report.results if r.id == "WEB-020")
    assert result.status is Status.SKIP and result.skip_reason is SkipReason.UNVERIFIED


# frob:tests python/sadi/doctor/hostprobe.py::windows_fstype
# frob:tests python/sadi/doctor/hostprobe.py::windows_long_paths
# frob:tests python/sadi/doctor/hostprobe.py::windows_default_browser
def test_windows_readers_answer_none_off_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    """The registry and volume readers return None when not running on Windows."""
    monkeypatch.setattr(hostprobe.sys, "platform", "linux")
    assert hostprobe.windows_fstype("/tmp") is None
    assert hostprobe.windows_long_paths() is None
    assert hostprobe.windows_default_browser() is None


# frob:tests python/sadi/doctor/hostprobe.py::web_bundle_version
def test_web_bundle_version_reads_version_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """version.json's sadi field is returned; absent or malformed files give None."""
    dist = tmp_path / "web" / "dist"
    dist.mkdir(parents=True)
    monkeypatch.setattr(hostprobe, "__file__", str(tmp_path / "doctor" / "hostprobe.py"))
    assert hostprobe.web_bundle_version() is None
    (dist / "version.json").write_text("{not json", encoding="utf-8")
    assert hostprobe.web_bundle_version() is None
    (dist / "version.json").write_text('{"sadi": "1.2.3"}', encoding="utf-8")
    assert hostprobe.web_bundle_version() == "1.2.3"


# frob:tests python/sadi/doctor/hostprobe.py::build_target
def test_build_target_is_none_without_attribute(monkeypatch: pytest.MonkeyPatch) -> None:
    """A sadi_py without BUILD_TARGET (or a str one) maps to None or the string."""
    import types

    fake = types.ModuleType("sadi_py")
    monkeypatch.setitem(__import__("sys").modules, "sadi_py", fake)
    assert hostprobe.build_target() is None
    fake.__dict__["BUILD_TARGET"] = "x86_64-unknown-linux-gnu"
    assert hostprobe.build_target() == "x86_64-unknown-linux-gnu"


# frob:tests python/sadi/doctor/hostprobe.py::launch_hit
def test_launch_hit_true_when_browser_connects(monkeypatch: pytest.MonkeyPatch) -> None:
    """launch_hit is True when the opened URL is fetched, False when nothing connects."""
    import urllib.request
    from threading import Thread

    def fetch(url: str) -> bool:
        Thread(target=lambda: urllib.request.urlopen(url, timeout=5).read()).start()
        return True

    monkeypatch.setattr(hostprobe.webbrowser, "open", fetch)
    assert hostprobe.launch_hit(5.0) is True
    monkeypatch.setattr(hostprobe.webbrowser, "open", lambda url: True)
    assert hostprobe.launch_hit(0.1) is False
    monkeypatch.setattr(hostprobe.webbrowser, "open", lambda url: False)
    assert hostprobe.launch_hit(0.1) is False


# frob:tests python/sadi/doctor/probes.py::Probes.build_target
# frob:tests python/sadi/doctor/probes.py::Probes.long_paths_enabled
# frob:tests python/sadi/doctor/probes.py::Probes.web_bundle_version
# frob:tests python/sadi/doctor/probes.py::Probes.browser_version
# frob:tests python/sadi/doctor/probes.py::Probes.browser_launch_hit
# frob:tests python/sadi/doctor/probes.py::RealProbes.build_target
# frob:tests python/sadi/doctor/probes.py::RealProbes.long_paths_enabled
# frob:tests python/sadi/doctor/probes.py::RealProbes.web_bundle_version
# frob:tests python/sadi/doctor/probes.py::RealProbes.browser_version
# frob:tests python/sadi/doctor/probes.py::RealProbes.browser_launch_hit
def test_real_probes_delegate_to_hostprobe(monkeypatch: pytest.MonkeyPatch) -> None:
    """RealProbes routes the new probes to hostprobe and parses `--version` output."""
    from sadi.doctor.probes import RealProbes

    real = RealProbes()
    monkeypatch.setattr(hostprobe, "build_target", lambda: "t")
    monkeypatch.setattr(hostprobe, "windows_long_paths", lambda: False)
    monkeypatch.setattr(hostprobe, "web_bundle_version", lambda: "9")
    monkeypatch.setattr(hostprobe, "launch_hit", lambda timeout: True)
    assert real.build_target() == "t"
    assert real.long_paths_enabled() is False
    assert real.web_bundle_version() == "9"
    assert real.browser_launch_hit(1.0) is True
    monkeypatch.setattr(real, "os_kind", lambda: Os.LINUX)
    monkeypatch.setattr(real, "_browser_name", lambda: "firefox")
    monkeypatch.setattr(real, "which", lambda name: "/usr/bin/firefox")
    run = CommandRun(
        argv=("firefox", "--version"), exit_code=0, stdout_tail="Mozilla Firefox 120.0\n"
    )
    monkeypatch.setattr(real, "run", lambda argv, **kw: Ok(run))
    assert real.browser_version() == ("firefox", 120)
    monkeypatch.setattr(real, "_browser_name", lambda: None)
    assert real.browser_version() is None


# frob:ticket 01M6XAY79MWPV07858YAKSBJQ6
# frob:tests python/sadi/doctor/render_text.py::render_result
def test_render_result_problem_has_fix_and_steps_but_pass_is_one_line() -> None:
    """A problem renders its Fix line and numbered steps; a pass renders a single line."""
    from sadi.doctor.render_text import render_result

    p = healthy()
    p.web_ver = "0.0.9"
    report = _run(p, Os.LINUX, data_root=ROOT)
    bad = next(r for r in report.results if r.id == "WEB-020")
    lines = render_result(bad)
    assert lines[0].startswith("[") and "WEB-020" in lines[0]
    assert any(ln.startswith("  Fix: ") for ln in lines)
    assert any(ln.startswith("  1. ") for ln in lines)
    assert any("Expect:" in ln for ln in lines)
    good = next(r for r in report.results if r.status is Status.PASS)
    assert render_result(good) == [f"[PASS] {good.id}  {good.headline}"]
