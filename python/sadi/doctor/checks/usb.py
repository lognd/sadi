"""USB checks: FTDI visibility, driver, node and permission (Linux/WSL; others are skipped).

Everything here is UNVERIFIED against hardware until the hardware session
(hardware-verification.md rows 1, 2); the checks only report observations.
"""

# frob:ticket 01M6WA9WYE9D71BBA7AV3H5CGF
from __future__ import annotations

import re

from sadi.doctor.registry import Ctx, Fix, Outcome, check, fail, ok, remedy, skip
from sadi.doctor.schema import Command, Layer, Mutates, Os, Severity, SkipReason, Step
from sadi.doctor.steps import action, cmd, manual

FTDI_VID = "0403"
FTDI_ALLOW_LIST = ("6010", "6014", "6001")
SYSFS_USB = "/sys/bus/usb/devices"
USBIPD_PATHS = ("usbipd.exe", "/mnt/c/Windows/System32/usbipd.exe")
_USBIPD_LINE = re.compile(
    r"^(?P<busid>\S+)\s+(?P<vidpid>[0-9a-f]{4}:[0-9a-f]{4})\s+(?P<name>.*?)\s+(?P<state>Not shared|Shared|Attached.*)$",
    re.IGNORECASE,
)
_LINUXISH = (Os.LINUX, Os.WSL)
_NOT_IMPLEMENTED = "USB probing is only implemented for Linux and WSL so far"


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
    exe = next((p for p in USBIPD_PATHS if ctx.probes.which(p) or ctx.probes.exists(p)), None)
    if exe is None:
        return []
    res = ctx.probes.run([exe, "list"])
    if res.is_err:
        return []
    rows: list[tuple[str, str]] = []
    for line in res.unwrap().stdout_tail.splitlines():
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
    "Linux: /sys/bus/usb/devices idVendor 0403; WSL also `usbipd.exe list`",
    applies_to=frozenset({Os.LINUX, Os.WSL, Os.MACOS, Os.WINDOWS}),
)
def usb_020(ctx: Ctx) -> Outcome:
    """Find the FTDI converter as the OS sees it."""
    if ctx.os not in _LINUXISH:
        return skip(SkipReason.UNVERIFIED, _NOT_IMPLEMENTED)
    devices = ctx.probes.listdir(SYSFS_USB)
    if devices is None and ctx.os is Os.LINUX:
        return skip(SkipReason.TOOL_MISSING, "/sys/bus/usb/devices is not readable")
    found = ftdi_sysfs(ctx)
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
                cmd(ctx.os, "lsusb"),
                if_not="Install the tool with your package manager (usbutils) and repeat.",
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
                cmd(ctx.os, "lsusb -d 0403:"),
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
    return target.rsplit("/", 1)[-1] if target else None


@check(
    "USB-030",
    Layer.USB,
    "Driver bound: VCP (ftdi_sio)",
    Severity.ERROR,
    {"no-driver": "The kernel serial driver ftdi_sio is not bound to the device"},
    "/sys/bus/usb/devices/<id>/<id>:1.0/driver symlink (Linux/WSL)",
    depends_on=("USB-020",),
)
def usb_030(ctx: Ctx) -> Outcome:
    """Check the device is claimed by the serial driver."""
    if ctx.os not in _LINUXISH:
        return skip(SkipReason.UNVERIFIED, _NOT_IMPLEMENTED)
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
    """Load ftdi_sio."""
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
    "/dev/serial/by-id/usb-FTDI_* and /dev/ttyUSB* (Linux/WSL)",
    depends_on=("USB-030",),
)
def usb_040(ctx: Ctx) -> Outcome:
    """Find the serial node."""
    if ctx.os not in _LINUXISH:
        return skip(SkipReason.UNVERIFIED, _NOT_IMPLEMENTED)
    nodes = [f"/dev/{n}" for n in ctx.probes.listdir("/dev") or [] if n.startswith("ttyUSB")]
    if not nodes:
        return fail("node-missing", "No /dev/ttyUSB* node found")
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
                cmd(ctx.os, "dmesg | tail -n 20"),
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
    "os.access on /dev/ttyUSB*, node group, os.getgroups (no open is attempted)",
    depends_on=("USB-040",),
)
def usb_050(ctx: Ctx) -> Outcome:
    """Check read/write access without opening the port."""
    if ctx.os not in _LINUXISH:
        return skip(SkipReason.UNVERIFIED, _NOT_IMPLEMENTED)
    nodes = [f"/dev/{n}" for n in ctx.probes.listdir("/dev") or [] if n.startswith("ttyUSB")]
    if not nodes:
        return skip(SkipReason.PREREQUISITE_FAILED, "No serial node")
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
                cmd(ctx.os, f"sudo usermod -aG {group} $USER"),
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
