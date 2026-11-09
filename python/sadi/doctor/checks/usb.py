"""USB checks: tool, FTDI visibility, driver, node, permission, holders, latency, usbipd.

Linux and WSL read sysfs, macOS reads system_profiler and /dev/cu.usbserial-*, Windows
reads PowerShell Get-PnpDevice and SerialPort names; all of it through Probes.run.

Everything here is UNVERIFIED against hardware until the hardware session
(hardware-verification.md rows 1, 2); the checks only report observations.
"""

# frob:ticket 01M6WA9WYE9D71BBA7AV3H5CGF
from __future__ import annotations

import re

from sadi.doctor.registry import Ctx, Fix, Outcome, check, fail, ok, remedy, skip, warn
from sadi.doctor.schema import Command, Layer, Mutates, Os, Severity, SkipReason, Step
from sadi.doctor.steps import action, cmd, manual
from sadi.logging_setup import get_logger

_log = get_logger(__name__)

FTDI_VID = "0403"
FTDI_ALLOW_LIST = ("6010", "6014", "6001")
SYSFS_USB = "/sys/bus/usb/devices"
USBIPD_PATHS = ("usbipd.exe", "/mnt/c/Windows/System32/usbipd.exe")
_USBIPD_LINE = re.compile(
    r"^(?P<busid>\S+)\s+(?P<vidpid>[0-9a-f]{4}:[0-9a-f]{4})\s+(?P<name>.*?)\s+(?P<state>Not shared|Shared|Attached.*)$",
    re.IGNORECASE,
)
_LINUXISH = (Os.LINUX, Os.WSL)
_DEV = "/dev"
_MAC_NODE_PREFIX = "cu.usbserial-"
_LATENCY_FMT = "/sys/bus/usb-serial/devices/{node}/latency_timer"
_UDEV_RULE = "/etc/udev/rules.d/99-sadi.rules"
_PS_BASE = ("powershell", "-NoProfile", "-NonInteractive", "-Command")
PS_FTDI = (
    "Get-PnpDevice -PresentOnly | Where-Object InstanceId -like 'USB\\VID_0403*' "
    "| Select-Object -ExpandProperty InstanceId"
)
PS_VCP_PORTS = (
    "Get-PnpDevice -Class Ports -PresentOnly | Where-Object InstanceId -like 'FTDIBUS\\VID_0403*' "
    "| Select-Object -ExpandProperty FriendlyName"
)
PS_VCP_STATUS = PS_VCP_PORTS.replace("FriendlyName", "Status")
PS_PORT_NAMES = "[System.IO.Ports.SerialPort]::GetPortNames()"
HOLDER_NAMES = ("LabVIEW", "FT_Prog", "NIMAX", "putty", "TeraTerm", "sadi")
PS_HOLDERS = (
    f"Get-Process | Where-Object {{ $_.ProcessName -match '{'|'.join(HOLDER_NAMES)}' }} "
    "| Select-Object -ExpandProperty ProcessName"
)
_MAC_PID = re.compile(r"Product ID: 0x(?P<pid>[0-9a-f]{4})\s+Vendor ID: 0x0403", re.IGNORECASE)
_WIN_PID = re.compile(r"VID_0403&PID_(?P<pid>[0-9A-F]{4})", re.IGNORECASE)
_COM = re.compile(r"^COM\d+$", re.IGNORECASE)
_DROP = re.compile(r"(vhci_hcd|usbip).*(disconnect|detach|error|fail|unable)", re.IGNORECASE)
_KCONFIG = "^CONFIG_(USB_SERIAL_FTDI_SIO|USB_VHCI_HCD)="
_USBIPD_MIN_MAJOR = 4
_DMESG_LINES = 200


def _stdout(ctx: Ctx, argv: list[str]) -> str | None:
    """Run a read-only command; return its stdout tail, or None when it failed or exited non-zero."""
    res = ctx.probes.run(argv)
    if res.is_err:
        _log.debug("usb probe %s failed: %s", argv[0], res.unwrap_err())
        return None
    run = res.unwrap()
    return run.stdout_tail if run.exit_code == 0 else None


def _ps(ctx: Ctx, script: str) -> list[str] | None:
    """Run a PowerShell one-liner; return its non-empty stdout lines, or None when it failed."""
    out = _stdout(ctx, [*_PS_BASE, script])
    return None if out is None else [ln.strip() for ln in out.splitlines() if ln.strip()]


def serial_nodes(ctx: Ctx) -> list[str]:
    """Return the serial node names for this OS (ttyUSB*, cu.usbserial-*, COMn)."""
    if ctx.os is Os.WINDOWS:
        return [n for n in _ps(ctx, PS_PORT_NAMES) or [] if _COM.match(n)]
    prefix = _MAC_NODE_PREFIX if ctx.os is Os.MACOS else "ttyUSB"
    return [f"{_DEV}/{n}" for n in ctx.probes.listdir(_DEV) or [] if n.startswith(prefix)]


def ftdi_devices(ctx: Ctx) -> list[tuple[str, str]] | None:
    """Return (id, product id) per FTDI device the OS sees, or None when it cannot enumerate."""
    if ctx.os in _LINUXISH:
        return ftdi_sysfs(ctx)
    if ctx.os is Os.MACOS:
        out = _stdout(ctx, ["system_profiler", "SPUSBDataType"])
        if out is None:
            return None
        return [(f"usb-{i}", m["pid"].lower()) for i, m in enumerate(_MAC_PID.finditer(out))]
    lines = _ps(ctx, PS_FTDI)
    if lines is None:
        return None
    pids = {m["pid"].lower(): ln for ln in lines if (m := _WIN_PID.search(ln))}
    return [(ln, pid) for pid, ln in pids.items()]


def _usbipd_exe(ctx: Ctx) -> str | None:
    """Return the usbipd executable that resolves (PATH or the Windows System32 path), if any."""
    return next(
        (p for p in USBIPD_PATHS if bool(ctx.probes.which(p)) or ctx.probes.exists(p)), None
    )


def _usbipd_major(ctx: Ctx, exe: str) -> int | None:
    """Return usbipd's major version from `--version`, or None when unreadable."""
    out = _stdout(ctx, [exe, "--version"])
    m = re.search(r"(\d+)\.\d+", out or "")
    return int(m[1]) if m else None


def _list_command(os: Os) -> str:
    """Return the OS-native one-liner that lists FTDI USB devices."""
    if os is Os.MACOS:
        return "system_profiler SPUSBDataType"
    if os is Os.WINDOWS:
        return (
            "Get-PnpDevice -PresentOnly | Where-Object InstanceId -like 'USB\\VID_0403*' "
            "| Format-Table -AutoSize"
        )
    return "lsusb -d 0403:"


def _nodes_command(os: Os) -> str:
    """Return the OS-native one-liner that lists serial nodes."""
    if os is Os.MACOS:
        return "ls /dev/cu.usbserial-*"
    if os is Os.WINDOWS:
        return PS_PORT_NAMES
    return "ls /dev/ttyUSB*"


def ftdi_sysfs(ctx: Ctx) -> list[tuple[str, str]]:
    """Return (sysfs dir name, product id) for each FTDI device the kernel sees."""
    found: list[tuple[str, str]] = []
    for name in ctx.probes.listdir(SYSFS_USB) or []:
        if ":" in name:
            continue
        vid = (ctx.probes.read_text(f"{SYSFS_USB}/{name}/idVendor") or "").strip().lower()
        if vid == FTDI_VID:
            pid = (ctx.probes.read_text(f"{SYSFS_USB}/{name}/idProduct") or "").strip().lower()
            found.append((name, pid))
    return found


def usbipd_ftdi(ctx: Ctx) -> list[tuple[str, str]]:
    """Return (busid, state) for FTDI devices that usbipd.exe lists (WSL only)."""
    exe = _usbipd_exe(ctx)
    out = _stdout(ctx, [exe, "list"]) if exe is not None else None
    rows: list[tuple[str, str]] = []
    for line in (out or "").splitlines():
        m = _USBIPD_LINE.match(line.strip())
        if m and m["vidpid"].lower().startswith(FTDI_VID):
            rows.append((m["busid"], m["state"]))
    return rows


@check(
    "USB-020",
    Layer.USB,
    "FTDI device visible to the OS",
    Severity.ERROR,
    {
        "no-device": "No FTDI device is enumerated",
        "device-on-windows-side": "WSL: usbipd lists the device but it is not shared",
        "shared-not-attached": "WSL: usbipd shares the device but it is not attached",
        "unknown-ftdi-pid": "An FTDI device with a product id outside the allow list",
    },
    "Linux: /sys/bus/usb/devices idVendor 0403; WSL also `usbipd.exe list`; "
    "macOS: system_profiler SPUSBDataType; Windows: Get-PnpDevice",
    applies_to=frozenset({Os.LINUX, Os.WSL, Os.MACOS, Os.WINDOWS}),
)
def usb_020(ctx: Ctx) -> Outcome:
    """Find the FTDI converter as the OS sees it."""
    devices = ctx.probes.listdir(SYSFS_USB)
    if devices is None and ctx.os is Os.LINUX:
        return skip(SkipReason.TOOL_MISSING, "/sys/bus/usb/devices is not readable")
    found = ftdi_devices(ctx)
    if found is None:
        return skip(SkipReason.TOOL_MISSING, "The OS USB enumeration command failed")
    if found:
        unknown = [pid for _, pid in found if pid not in FTDI_ALLOW_LIST]
        if len(unknown) == len(found):
            return fail(
                "unknown-ftdi-pid",
                f"FTDI product id {unknown[0]} is not a known SADI board",
                pids=unknown,
            )
        return ok(
            f"FTDI device {found[0][0]} ({found[0][1]}) is visible", devices=[d for d, _ in found]
        )
    if ctx.os is Os.WSL:
        rows = usbipd_ftdi(ctx)
        for busid, state in rows:
            if state.lower() == "not shared":
                return fail(
                    "device-on-windows-side", f"Device {busid} is still on Windows", busid=busid
                )
            if state.lower() == "shared":
                return fail(
                    "shared-not-attached", f"Device {busid} is shared but not attached", busid=busid
                )
    return fail("no-device", "No FTDI device found; is the board plugged in and powered?")


@remedy("USB-020", "no-device")
def _usb_020_none(ctx: Ctx, out: Outcome) -> Fix:
    """Check cable and power."""
    return Fix(
        "Get the board enumerated",
        (
            manual(
                "Plug in the board's USB cable and its power supply; try another cable or port.",
                "The board's power light is on.",
                if_not="A cable without data wires is common; use a known data cable.",
            ),
            action(
                "List USB devices.",
                "A line containing 0403 (FTDI).",
                cmd(ctx.os, _list_command(ctx.os)),
                if_not="Linux: install usbutils with your package manager and repeat.",
            ),
        ),
    )


@remedy("USB-020", "device-on-windows-side")
def _usb_020_win(ctx: Ctx, out: Outcome) -> Fix:
    """Share and attach through usbipd (administrator for bind)."""
    busid = str(out.facts.get("busid", "<busid>"))
    win = Os.WINDOWS
    return Fix(
        "Hand the device to WSL with usbipd",
        (
            action(
                "In an administrator PowerShell window on Windows, share the device once.",
                "No error; `usbipd list` shows the device as Shared.",
                cmd(win, f"usbipd bind --busid {busid}"),
                mutates=Mutates.SYSTEM,
                changes="Marks the device as shareable with WSL; persists until unbound.",
                if_not="Install usbipd-win 4.0 or newer from its GitHub releases.",
            ),
            action(
                "In a normal PowerShell window, attach it to WSL.",
                "No error; `usbipd list` shows the device as Attached.",
                cmd(win, f"usbipd attach --wsl --busid {busid}"),
                mutates=Mutates.SYSTEM,
                changes="Moves the device from Windows to WSL until it is unplugged.",
            ),
        ),
    )


# frob:ticket 01M6WMZHNS2E0QNW7KFZ1GAYMZ
def _wsl_attach(ctx: Ctx, busid: str) -> tuple[Command, ...]:
    """Return the fixable interop attach command on WSL only; bind (Administrator) is never fixable."""
    if ctx.os is not Os.WSL:
        return ()
    return (cmd(ctx.os, f"usbipd.exe attach --wsl --busid {busid}", fixable=True),)


# frob:ticket 01M6WMZHNS2E0QNW7KFZ1GAYMZ
def _udev_install(ctx: Ctx) -> tuple[Step, ...]:
    """Return the fixable udev rule install step (Linux/WSL), one subprocess per command."""
    if ctx.os not in _LINUXISH:
        return ()
    dest = "/etc/udev/rules.d/99-sadi.rules"
    return (
        action(
            "Install the SADI udev rule (run from the SADI checkout).",
            f"{dest} exists and `udevadm trigger` prints nothing.",
            cmd(ctx.os, f"sudo install -m 0644 packaging/udev/99-sadi.rules {dest}", fixable=True),
            cmd(ctx.os, "sudo udevadm control --reload-rules", fixable=True),
            cmd(ctx.os, "sudo udevadm trigger", fixable=True),
            mutates=Mutates.SYSTEM,
            changes="Writes /etc/udev/rules.d/99-sadi.rules and reloads udev rules.",
        ),
    )


@remedy("USB-020", "shared-not-attached")
def _usb_020_shared(ctx: Ctx, out: Outcome) -> Fix:
    """Attach a shared device."""
    busid = str(out.facts.get("busid", "<busid>"))
    return Fix(
        "Attach the shared device to WSL",
        (
            action(
                "In a normal PowerShell window on Windows, attach it.",
                "No error; `usbipd list` shows the device as Attached.",
                cmd(Os.WINDOWS, f"usbipd attach --wsl --busid {busid}"),
                *_wsl_attach(ctx, busid),
                mutates=Mutates.SYSTEM,
                changes="Moves the device from Windows to WSL until it is unplugged.",
            ),
        ),
    )


@remedy("USB-020", "unknown-ftdi-pid")
def _usb_020_pid(ctx: Ctx, out: Outcome) -> Fix:
    """Explain an unknown FTDI part."""
    return Fix(
        "Confirm this is the right board",
        (
            action(
                "Show the FTDI device details.",
                "Product id is 6010, 6014 or 6001 for a SADI board.",
                cmd(ctx.os, _list_command(ctx.os)),
            ),
            manual(
                "If it is another FTDI gadget, unplug it and plug in the SADI board.",
                "The board's product id is on the allow list.",
            ),
        ),
    )


def _driver_link(ctx: Ctx, dev: str) -> str | None:
    """Return the bound driver name of interface 1.0 of a device, if any."""
    target = ctx.probes.readlink(f"{SYSFS_USB}/{dev}/{dev}:1.0/driver")
    return target.rsplit("/", 1)[-1] if target is not None and target else None


@check(
    "USB-030",
    Layer.USB,
    "Driver bound: VCP (ftdi_sio)",
    Severity.ERROR,
    {"no-driver": "The kernel serial driver ftdi_sio is not bound to the device"},
    "/sys/bus/usb/devices/<id>/<id>:1.0/driver symlink (Linux/WSL); "
    "macOS: /dev/cu.usbserial-*; Windows: Get-PnpDevice class Ports",
    depends_on=("USB-020",),
)
def usb_030(ctx: Ctx) -> Outcome:
    """Check the device is claimed by the serial driver."""
    if ctx.os is Os.MACOS:
        nodes = serial_nodes(ctx)
        if nodes:
            return ok("The macOS FTDI driver created a serial node", nodes=nodes)
        return fail("no-driver", "No /dev/cu.usbserial-* node: the FTDI driver is not active")
    if ctx.os is Os.WINDOWS:
        ports = _ps(ctx, PS_VCP_PORTS)
        if ports is None:
            return skip(SkipReason.TOOL_MISSING, "Get-PnpDevice could not be run")
        if any("COM" in p.upper() for p in ports):
            return ok("A VCP COM port is present", ports=ports)
        return fail("no-driver", "The FTDI device has no VCP COM port (driver not loaded)")
    found = ftdi_sysfs(ctx)
    if not found:
        return skip(SkipReason.PREREQUISITE_FAILED, "No FTDI device in sysfs")
    dev = found[0][0]
    driver = _driver_link(ctx, dev)
    if driver == "ftdi_sio":
        return ok("ftdi_sio is bound", device=dev, driver=driver)
    return fail(
        "no-driver", f"Device {dev} is bound to {driver or 'no driver'}", device=dev, driver=driver
    )


@remedy("USB-030", "no-driver")
def _usb_030_driver(ctx: Ctx, out: Outcome) -> Fix:
    """Load ftdi_sio (Linux/WSL); replug on macOS; enable VCP in Device Manager on Windows."""
    if ctx.os is Os.MACOS:
        return Fix(
            "Get the macOS FTDI driver to claim the device",
            (
                manual(
                    "Unplug the board's USB cable, wait 5 seconds, plug it in again.",
                    "A /dev/cu.usbserial-* node appears.",
                    if_not="Remove any legacy FTDI kext and install the current FTDI VCP driver.",
                ),
                action(
                    "List the serial nodes.",
                    "A line starting with /dev/cu.usbserial-.",
                    cmd(ctx.os, _nodes_command(ctx.os)),
                ),
            ),
        )
    if ctx.os is Os.WINDOWS:
        return Fix(
            "Load the FTDI VCP driver",
            (
                manual(
                    "In Device Manager open Universal Serial Bus controllers, double-click "
                    "USB Serial Converter, Advanced tab, tick Load VCP, then replug the board.",
                    "Ports (COM & LPT) lists USB Serial Port (COMn).",
                    mutates=Mutates.SYSTEM,
                    changes="Switches the FTDI device from the D2XX driver to the VCP driver.",
                    if_not="Install the FTDI VCP driver from ftdichip.com and replug.",
                ),
                action(
                    "List the VCP ports.",
                    "A row with FriendlyName containing COM.",
                    cmd(ctx.os, PS_VCP_PORTS),
                ),
            ),
        )
    steps = [
        action(
            "Load the FTDI serial driver.",
            "No output.",
            cmd(ctx.os, "sudo modprobe ftdi_sio"),
            mutates=Mutates.SYSTEM,
            changes="Loads a kernel module until reboot.",
            if_not=(
                "WSL: the stock kernel may lack ftdi_sio; build a custom WSL kernel with CONFIG_USB_SERIAL_FTDI_SIO."
                if ctx.os is Os.WSL
                else "Check `dmesg | tail` for the reason."
            ),
        ),
        action(
            "Confirm the module is loaded.",
            "A line starting with ftdi_sio.",
            cmd(ctx.os, "lsmod | grep ftdi_sio"),
        ),
    ]
    return Fix("Load the FTDI driver", tuple(steps))


@check(
    "USB-040",
    Layer.USB,
    "Serial node exists",
    Severity.ERROR,
    {"node-missing": "Driver is bound but no /dev/ttyUSB* node exists"},
    "/dev/serial/by-id/usb-FTDI_* and /dev/ttyUSB* (Linux/WSL); "
    "macOS: /dev/cu.usbserial-*; Windows: SerialPort.GetPortNames",
    depends_on=("USB-030",),
)
def usb_040(ctx: Ctx) -> Outcome:
    """Find the serial node."""
    nodes = serial_nodes(ctx)
    if not nodes:
        return fail("node-missing", "No serial node found")
    return ok(f"Serial node {nodes[0]}", nodes=nodes)


@remedy("USB-040", "node-missing")
def _usb_040_node(ctx: Ctx, out: Outcome) -> Fix:
    """Replug to create the node."""
    return Fix(
        "Make the OS create the node",
        (
            manual(
                "Unplug the board's USB cable, wait 5 seconds, plug it in again (WSL: also re-run the usbipd attach).",
                "A new /dev/ttyUSB0 appears.",
            ),
            action(
                "Watch the kernel log.",
                "A line saying the FTDI device is now attached to ttyUSB0.",
                cmd(
                    ctx.os, "dmesg | tail -n 20" if ctx.os in _LINUXISH else _nodes_command(ctx.os)
                ),
            ),
        ),
    )


@check(
    "USB-050",
    Layer.USB,
    "Permission to open the serial node",
    Severity.ERROR,
    {
        "not-in-group": "Your user is not in the node's group",
        "node-not-accessible": "You are in the group but the node is still not read/write",
    },
    "os.access on /dev/ttyUSB*, node group, os.getgroups (no open is attempted); "
    "Windows: Get-PnpDevice Status instead of an open",
    depends_on=("USB-040",),
)
def usb_050(ctx: Ctx) -> Outcome:
    """Check read/write access without opening the port."""
    nodes = serial_nodes(ctx)
    if not nodes:
        return skip(SkipReason.PREREQUISITE_FAILED, "No serial node")
    if ctx.os is Os.WINDOWS:
        states = _ps(ctx, PS_VCP_STATUS)
        if states is None:
            return skip(SkipReason.TOOL_MISSING, "Get-PnpDevice could not be run")
        if any(s.upper() == "OK" for s in states):
            return ok(f"{nodes[0]} reports status OK", node=nodes[0])
        return fail("node-not-accessible", f"{nodes[0]} does not report status OK", node=nodes[0])
    allowed, group = ctx.probes.node_access(nodes[0])
    if allowed:
        return ok(f"You can open {nodes[0]}", node=nodes[0], group=group)
    if group is not None and group not in ctx.probes.user_groups():
        return fail("not-in-group", f"You are not in group {group}", node=nodes[0], group=group)
    return fail(
        "node-not-accessible",
        f"{nodes[0]} is not readable and writable",
        node=nodes[0],
        group=group,
    )


@remedy("USB-050", "not-in-group")
def _usb_050_group(ctx: Ctx, out: Outcome) -> Fix:
    """Add the user to the node's group."""
    group = str(out.facts.get("group") or "dialout")
    return Fix(
        f"Join the {group} group",
        (
            action(
                f"Add your user to {group}.",
                "No output.",
                cmd(
                    ctx.os,
                    f"sudo dseditgroup -o edit -a $USER -t user {group}"
                    if ctx.os is Os.MACOS
                    else f"sudo usermod -aG {group} $USER",
                ),
                mutates=Mutates.SYSTEM,
                changes=f"Adds your account to the {group} group.",
            ),
            manual(
                "Log out and log in again (WSL: run `wsl --shutdown` in PowerShell, then reopen).",
                f"`id` lists {group}.",
            ),
        ),
    )


@remedy("USB-050", "node-not-accessible")
def _usb_050_node(ctx: Ctx, out: Outcome) -> Fix:
    """Inspect the node permissions."""
    node = str(out.facts.get("node") or "/dev/ttyUSB0")
    if ctx.os is Os.WINDOWS:
        return Fix(
            "Get the COM port to report status OK",
            (
                action(
                    "Show the VCP port status.",
                    "Status OK.",
                    cmd(ctx.os, PS_VCP_STATUS),
                    if_not="Replug the board; if it persists reinstall the FTDI VCP driver.",
                ),
                manual(
                    "Close any program that has the port open (LabVIEW, PuTTY, Tera Term).",
                    "The port is free.",
                ),
            ),
        )
    return Fix(
        "Inspect the node permissions",
        (
            action(
                "Show the node's owner, group and mode.",
                "Mode crw-rw---- and a group you belong to.",
                cmd(ctx.os, f"ls -l {node}"),
            ),
            action(
                "As a stopgap, grant your user access until the next replug.",
                "No output.",
                cmd(ctx.os, f"sudo chmod 660 {node}"),
                mutates=Mutates.SYSTEM,
                changes="Changes the node mode until the device is replugged.",
                alt="Install a udev rule for a permanent fix (packaging/udev).",
            ),
            *_udev_install(ctx),
        ),
    )


# frob:ticket 01M6WJHVXTWDD0RA55508QAN2W
@check(
    "USB-010",
    Layer.USB,
    "USB enumeration tool available",
    Severity.WARNING,
    {
        "no-enumeration-tool": "No tool to enumerate USB devices was found",
        "usbipd-missing": "WSL: usbipd.exe is not resolvable from WSL",
        "usbipd-old": "WSL: usbipd is older than 4.0 (different CLI)",
    },
    "Linux: lsusb on PATH or /sys/bus/usb/devices readable; macOS: system_profiler; "
    "Windows: powershell; WSL: usbipd.exe (PATH or /mnt/c/Windows/System32) and its --version",
)
def usb_010(ctx: Ctx) -> Outcome:
    """Check that this OS has a way to list USB devices (and usbipd on WSL)."""
    if ctx.os is Os.WSL:
        exe = _usbipd_exe(ctx)
        if exe is None:
            return fail("usbipd-missing", "usbipd.exe is not resolvable from WSL")
        major = _usbipd_major(ctx, exe)
        if major is not None and major < _USBIPD_MIN_MAJOR:
            return warn("usbipd-old", f"usbipd major version {major} is older than 4", major=major)
    if ctx.os is Os.MACOS:
        have = bool(ctx.probes.which("system_profiler"))
    elif ctx.os is Os.WINDOWS:
        have = bool(ctx.probes.which("powershell"))
    else:
        have = bool(ctx.probes.which("lsusb")) or ctx.probes.listdir(SYSFS_USB) is not None
    if not have:
        _log.warning("no USB enumeration tool on %s", ctx.os)
        return warn("no-enumeration-tool", "No USB enumeration tool found")
    return ok("A USB enumeration tool is available")


@remedy("USB-010", "no-enumeration-tool")
def _usb_010_tool(ctx: Ctx, out: Outcome) -> Fix:
    """Install the OS's USB listing tool."""
    if ctx.os is Os.MACOS:
        step = manual(
            "system_profiler ships with macOS; repair the install with `softwareupdate`.",
            "`system_profiler -listDataTypes` lists SPUSBDataType.",
        )
    elif ctx.os is Os.WINDOWS:
        step = manual(
            "Install Windows PowerShell (it ships with Windows) and add it to PATH.",
            "`powershell -Command $PSVersionTable` prints a version.",
        )
    else:
        step = action(
            "Install usbutils.",
            "`lsusb` lists the root hubs.",
            cmd(ctx.os, "sudo apt install usbutils"),
            mutates=Mutates.SYSTEM,
            changes="Installs the usbutils package.",
            if_not="Use your distribution's package manager (dnf, pacman) instead of apt.",
        )
    return Fix("Get a USB enumeration tool", (step,))


@remedy("USB-010", "usbipd-missing")
def _usb_010_missing(ctx: Ctx, out: Outcome) -> Fix:
    """Install usbipd-win on the Windows side."""
    return Fix(
        "Install usbipd-win",
        (
            action(
                "Install usbipd-win from an Administrator PowerShell on Windows.",
                "`usbipd --version` prints 4.x or newer.",
                cmd(Os.WINDOWS, "winget install --interactive --exact dorssel.usbipd-win"),
                mutates=Mutates.SYSTEM,
                changes="Installs usbipd-win on Windows.",
                if_not="Download the installer from the usbipd-win releases page.",
            ),
            manual(
                "Reopen the WSL terminal so the Windows PATH is re-read.",
                "`usbipd.exe --version` works from WSL.",
            ),
        ),
    )


@remedy("USB-010", "usbipd-old")
def _usb_010_old(ctx: Ctx, out: Outcome) -> Fix:
    """Upgrade usbipd-win."""
    return Fix(
        "Upgrade usbipd-win",
        (
            action(
                "Upgrade usbipd-win from an Administrator PowerShell on Windows.",
                "`usbipd --version` prints 4.x or newer.",
                cmd(Os.WINDOWS, "winget upgrade --interactive --exact dorssel.usbipd-win"),
                mutates=Mutates.SYSTEM,
                changes="Upgrades usbipd-win on Windows.",
            ),
        ),
    )


def _holders(ctx: Ctx, node: str) -> list[str] | None:
    """Return 'name' per process holding the node open, or None when no tool could ask."""
    if ctx.os is Os.WINDOWS:
        return _ps(ctx, PS_HOLDERS)
    out = _stdout(ctx, ["lsof", "-F", "pc", node])
    if out is not None:
        return [ln[1:] for ln in out.splitlines() if ln.startswith("c")]
    if _stdout(ctx, ["fuser", node]) is not None:
        return ["unknown"]
    return None


def _modemmanager_active(ctx: Ctx) -> bool:
    """Return True when ModemManager runs and no SADI udev rule tells it to ignore the device."""
    if ctx.os is not Os.LINUX:
        return False
    out = _stdout(ctx, ["systemctl", "is-active", "ModemManager"])
    if (out or "").strip() != "active":
        return False
    return "ID_MM_DEVICE_IGNORE" not in (ctx.probes.read_text(_UDEV_RULE) or "")


@check(
    "USB-060",
    Layer.USB,
    "Serial node not held by another program",
    Severity.ERROR,
    {
        "held-by-sadi": "SADI itself has the node open",
        "held-by-labview": "LabVIEW has the node open",
        "held-by-other": "Another program has the node open",
        "modemmanager-probing": "ModemManager is probing serial devices (no ID_MM_DEVICE_IGNORE rule)",
    },
    "Linux/WSL/macOS: lsof -F pc (then fuser) on the node; Windows: Get-Process names in a known "
    "list; Linux: systemctl is-active ModemManager and 99-sadi.rules",
    depends_on=("USB-040",),
)
def usb_060(ctx: Ctx) -> Outcome:
    """Find programs that hold the serial node open."""
    nodes = serial_nodes(ctx)
    if not nodes:
        return skip(SkipReason.PREREQUISITE_FAILED, "No serial node")
    names = _holders(ctx, nodes[0])
    mm = _modemmanager_active(ctx)
    if names is None and not mm:
        return skip(SkipReason.TOOL_MISSING, "No lsof, fuser or Get-Process available")
    names = [n for n in names or [] if n.lower() != "modemmanager"] + (
        [] if mm else [n for n in names or [] if n.lower() == "modemmanager"]
    )
    lowered = [n.lower() for n in names]
    if any("labview" in n for n in lowered):
        return fail("held-by-labview", "LabVIEW has the port open", holders=names)
    if any("sadi" not in n for n in lowered):
        return fail("held-by-other", f"{nodes[0]} is held by {', '.join(names)}", holders=names)
    if mm:
        return fail("modemmanager-probing", "ModemManager is probing the port")
    if names:
        return warn("held-by-sadi", "SADI has the port open", holders=names)
    return ok(f"{nodes[0]} is free")


@remedy("USB-060", "held-by-sadi")
def _usb_060_sadi(ctx: Ctx, out: Outcome) -> Fix:
    """Stop the running SADI instance (or expect the port to be busy)."""
    return Fix(
        "Stop the SADI process that owns the port",
        (
            manual(
                "In the running SADI press Stop, then close it (or leave it running and "
                "skip the active DEV checks).",
                "`sadi-doctor --check USB-060` passes.",
            ),
        ),
    )


@remedy("USB-060", "held-by-labview")
def _usb_060_labview(ctx: Ctx, out: Outcome) -> Fix:
    """Close the LabVIEW VI."""
    return Fix(
        "Close the LabVIEW VI",
        (
            manual(
                "Stop the VI and close LabVIEW (portability.md: it keeps the port open).",
                "The port is free.",
            ),
        ),
    )


@remedy("USB-060", "held-by-other")
def _usb_060_other(ctx: Ctx, out: Outcome) -> Fix:
    """Identify and close the other holder."""
    node = serial_nodes(ctx)[0] if serial_nodes(ctx) else "/dev/ttyUSB0"
    if ctx.os is Os.WINDOWS:
        listing = action(
            "List the likely holders.",
            "A process name from the known list.",
            cmd(ctx.os, PS_HOLDERS),
        )
    else:
        listing = action(
            "List the processes holding the node.",
            "A pid and command name.",
            cmd(ctx.os, f"lsof {node}"),
        )
    return Fix(
        "Close the program holding the port",
        (listing, manual("Close that program.", "The listing is empty.")),
    )


@remedy("USB-060", "modemmanager-probing")
def _usb_060_mm(ctx: Ctx, out: Outcome) -> Fix:
    """Tell ModemManager to ignore the SADI device (Linux only; elsewhere nothing applies)."""
    if ctx.os is not Os.LINUX:
        return Fix(
            "ModemManager only exists on Linux",
            (manual("Nothing to do on this OS.", "USB-060 passes."),),
        )
    return Fix(
        "Stop ModemManager probing the board",
        _udev_install(ctx)
        + (
            action(
                "Confirm ModemManager ignores the device.",
                "A line with ID_MM_DEVICE_IGNORE.",
                cmd(ctx.os, f"grep ID_MM_DEVICE_IGNORE {_UDEV_RULE}"),
                if_not="Reinstall the rule from packaging/udev/99-sadi.rules.",
            ),
        ),
    )


@check(
    "USB-070",
    Layer.USB,
    "FTDI latency timer",
    Severity.INFO,
    {"latency-not-2ms": "latency_timer is not 2 ms (hardware-verification.md row 1 is pending)"},
    "/sys/bus/usb-serial/devices/ttyUSBn/latency_timer (Linux and WSL); report only",
    applies_to=frozenset(_LINUXISH),
    depends_on=("USB-040",),
)
def usb_070(ctx: Ctx) -> Outcome:
    """Report the FTDI latency timer of each ttyUSB node."""
    nodes = [n.rsplit("/", 1)[-1] for n in serial_nodes(ctx)]
    if not nodes:
        return skip(SkipReason.PREREQUISITE_FAILED, "No serial node")
    values: dict[str, str] = {}
    for node in nodes:
        text = ctx.probes.read_text(_LATENCY_FMT.format(node=node))
        if text is not None:
            values[node] = text.strip()
    if not values:
        return skip(SkipReason.UNVERIFIED, "latency_timer is not readable")
    off = [f"{n}={v}" for n, v in values.items() if v != "2"]
    if off:
        return warn(
            "latency-not-2ms", f"latency_timer is {', '.join(off)} (expected 2)", latency=off
        )
    return ok("latency_timer is 2 ms", nodes=nodes)


@remedy("USB-070", "latency-not-2ms")
def _usb_070_latency(ctx: Ctx, out: Outcome) -> Fix:
    """Show how to set the latency timer to 2 ms."""
    if ctx.os not in _LINUXISH:
        return Fix(
            "Latency is only read on Linux and WSL",
            (manual("Nothing to do on this OS.", "USB-070 is not applicable."),),
        )
    return Fix(
        "Set the latency timer to 2 ms",
        (
            action(
                "Write 2 to the latency timer (until the next replug).",
                "No output.",
                cmd(ctx.os, "echo 2 | sudo tee /sys/bus/usb-serial/devices/ttyUSB0/latency_timer"),
                mutates=Mutates.SYSTEM,
                changes="Changes the FTDI latency timer until the device is replugged.",
                alt='Add ATTR{latency_timer}="2" to a udev rule for a permanent change.',
            ),
        ),
    )


def _kernel_config(ctx: Ctx) -> str | None:
    """Return the FTDI/VHCI lines of the running kernel config, or None when unreadable."""
    out = _stdout(ctx, ["zgrep", "-E", _KCONFIG, "/proc/config.gz"])
    if out is not None:
        return out
    release = _stdout(ctx, ["uname", "-r"])
    if release is None:
        return None
    return _stdout(ctx, ["grep", "-E", _KCONFIG, f"/boot/config-{release.strip()}"])


def _vhci_loaded(ctx: Ctx) -> bool:
    """Report whether vhci_hcd is loaded or built in, judged from sysfs rather than the config."""
    if ctx.probes.is_dir("/sys/module/vhci_hcd"):
        return True
    entries = ctx.probes.listdir("/sys/devices/platform") or []
    return any(name.startswith("vhci_hcd") for name in entries)


@check(
    "USB-080",
    Layer.USB,
    "usbipd attach health",
    Severity.ERROR,
    {
        "attached-no-node": "usbipd shows Attached but no /dev/ttyUSB node exists",
        "vhci-missing": "The WSL kernel lacks vhci_hcd (no USB/IP client; =y, =m or a loaded module count as present)",
        "attach-dropped": "dmesg shows the USB/IP attach was dropped",
    },
    "usbipd list Attached row; kernel config from /proc/config.gz or /boot/config-$(uname -r); "
    "dmesg last 200 lines for usbip or vhci_hcd errors",
    applies_to=frozenset({Os.WSL}),
)
def usb_080(ctx: Ctx) -> Outcome:
    """Check the WSL side of an attached usbipd device."""
    exe = _usbipd_exe(ctx)
    if exe is None:
        return skip(SkipReason.TOOL_MISSING, "usbipd.exe is not resolvable")
    rows = usbipd_ftdi(ctx)
    if not any(state.lower().startswith("attached") for _, state in rows):
        return skip(SkipReason.PREREQUISITE_FAILED, "No attached usbipd device (see USB-020)")
    config = _kernel_config(ctx)
    if not config:
        _log.info("USB-080: kernel config unreadable; not judging vhci_hcd from it")
    elif not re.search(r"^CONFIG_USB_VHCI_HCD=[ym]", config, re.MULTILINE):
        if _vhci_loaded(ctx):
            _log.info("USB-080: config lacks VHCI_HCD but vhci_hcd is present in sysfs; accepting")
        else:
            return fail("vhci-missing", "The kernel config lacks CONFIG_USB_VHCI_HCD")
    log = _stdout(ctx, ["dmesg"]) or ""
    dropped = [ln for ln in log.splitlines()[-_DMESG_LINES:] if _DROP.search(ln)]
    if dropped:
        return fail("attach-dropped", "dmesg shows a USB/IP error", lines=dropped[-3:])
    if not serial_nodes(ctx):
        return fail("attached-no-node", "Attached, but no /dev/ttyUSB node was created")
    return ok("The usbipd attach is healthy")


@remedy("USB-080", "attached-no-node")
def _usb_080_node(ctx: Ctx, out: Outcome) -> Fix:
    """Load ftdi_sio or fall back to a custom kernel."""
    return Fix(
        "Get a serial node for the attached device",
        (
            action(
                "Load the FTDI serial driver.",
                "No output.",
                cmd(ctx.os, "sudo modprobe ftdi_sio"),
                mutates=Mutates.SYSTEM,
                changes="Loads a kernel module until reboot.",
                if_not="Build a custom WSL kernel with CONFIG_USB_SERIAL_FTDI_SIO=y.",
            ),
            action(
                "Check that the node exists.",
                "A /dev/ttyUSB0 line.",
                cmd(ctx.os, _nodes_command(ctx.os)),
            ),
        ),
    )


@remedy("USB-080", "vhci-missing")
def _usb_080_vhci(ctx: Ctx, out: Outcome) -> Fix:
    """Point at a kernel with vhci_hcd."""
    return Fix(
        "Use a WSL kernel with USB/IP support",
        (
            manual(
                "Build or install a WSL kernel with CONFIG_USB_VHCI_HCD=y and CONFIG_USB_SERIAL_FTDI_SIO=y, "
                "point .wslconfig at it, then run `wsl --shutdown`.",
                "`zgrep VHCI /proc/config.gz` shows CONFIG_USB_VHCI_HCD=y.",
                mutates=Mutates.SYSTEM,
                changes="Replaces the WSL kernel.",
            ),
        ),
    )


@remedy("USB-080", "attach-dropped")
def _usb_080_dropped(ctx: Ctx, out: Outcome) -> Fix:
    """Re-attach the device."""
    return Fix(
        "Re-attach the device",
        (
            action(
                "Attach again.",
                "usbipd reports Attached.",
                *_wsl_attach(ctx, "<busid>"),
                cmd(ctx.os, "usbipd.exe list"),
                mutates=Mutates.SYSTEM,
                changes="Attaches the USB device to WSL.",
                alt="Run `usbipd attach --wsl --auto-attach --busid <busid>` for a persistent attach.",
            ),
        ),
    )
