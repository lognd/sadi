"""AD3 checks: the Digilent Analog Discovery 3 and its WaveForms runtime, per side.

Three sides exist and every outcome names the one it evaluated:

* ``linux``   - native Linux: sysfs and ``libdwf.so``.
* ``wsl``     - inside WSL: sysfs (device attached via usbipd) and ``libdwf.so``; the
  Windows side (``dwf.dll``, WaveForms, PnP) is read through ``powershell.exe`` interop.
* ``windows`` - native Windows: PowerShell ``Get-PnpDevice`` and ``dwf.dll`` in System32.

All checks are read-only; only ``sadi doctor fix --apply`` runs the fixable commands.
"""

# frob:ticket 01M6Z1E0F6PK6K2F6B9VC7QQWM
from __future__ import annotations

import os.path
from dataclasses import dataclass

from sadi.bench.ad3.consts import ENV_LIB_PATH
from sadi.bench.ad3.dll import candidate_names
from sadi.doctor.checks.ext import child_json
from sadi.doctor.checks.usb import _USBIPD_LINE, SYSFS_USB, USBIPD_PATHS
from sadi.doctor.registry import Ctx, Fix, Outcome, check, fail, ok, remedy, skip, warn
from sadi.doctor.schema import Layer, Mutates, Os, Severity, SkipReason, Step
from sadi.doctor.steps import action, cmd, manual
from sadi.logging_setup import get_logger

_log = get_logger(__name__)

AD3_VID = "1443"
AD3_PID = "7003"
DLL_WINDOWS = "C:\\Windows\\System32\\dwf.dll"
DLL_VIA_WSL = "/mnt/c/Windows/System32/dwf.dll"
POWERSHELL_PATHS = (
    "powershell.exe",
    "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe",
)
_PS_ARGS = ("-NoProfile", "-NonInteractive", "-Command")
_LIB_DIRS = ("/usr/lib", "/usr/lib/x86_64-linux-gnu", "/usr/local/lib", "/usr/lib64")
PS_AD3 = (
    f"Get-PnpDevice -PresentOnly | Where-Object InstanceId -like 'USB\\VID_{AD3_VID}&PID_{AD3_PID}*' "
    "| Select-Object -ExpandProperty InstanceId"
)
PS_PROCS = (
    "Get-Process -Name WaveForms*,Adept* -ErrorAction SilentlyContinue "
    "| Select-Object -ExpandProperty ProcessName"
)
_LINUX_PROCS = ["pgrep", "-il", "waveforms|adept"]
_DEPS = ("AD3-010",)
_OPEN_SCRIPT = (
    "import json\n"
    "from sadi.bench.ad3.dll import load_backend\n"
    "r = load_backend()\n"
    "if r.is_err:\n"
    "    print(json.dumps({'status': 'no-library', 'detail': str(r.unwrap_err().detail)}))\n"
    "    raise SystemExit(0)\n"
    "b = r.unwrap()\n"
    "e = b.enumerate_devices()\n"
    "if e.is_err or not e.unwrap():\n"
    "    print(json.dumps({'status': 'no-device', 'detail': ''}))\n"
    "    raise SystemExit(0)\n"
    "o = b.open(-1)\n"
    "if o.is_err:\n"
    "    print(json.dumps({'status': 'open-failed', 'detail': str(o.unwrap_err().detail)}))\n"
    "    raise SystemExit(0)\n"
    "b.close(o.unwrap())\n"
    "print(json.dumps({'status': 'ok', 'detail': ''}))\n"
)


@dataclass(frozen=True)
class Ad3Where:
    """Where the AD3 was seen: ``holder`` is 'self' (this side), 'windows', 'none' or 'unknown'."""

    side: str
    holder: str
    busid: str | None = None
    reason: str = ""


def side_of(ctx: Ctx) -> str:
    """Name the side this run evaluates: linux, wsl or windows (macOS never reaches a check)."""
    return {Os.WSL: "wsl", Os.WINDOWS: "windows"}.get(ctx.os, "linux")


def _powershell(ctx: Ctx) -> str | None:
    """Return the PowerShell executable for this OS (interop on WSL), or None when absent."""
    if ctx.os is Os.WINDOWS:
        return "powershell"
    if ctx.os is Os.WSL:
        return next(
            (p for p in POWERSHELL_PATHS if bool(ctx.probes.which(p)) or ctx.probes.exists(p)), None
        )
    return None


def _ps(ctx: Ctx, script: str) -> list[str] | None:
    """Run a PowerShell one-liner; return its non-empty stdout lines, or None when unavailable."""
    exe = _powershell(ctx)
    if exe is None:
        _log.info("AD3: no PowerShell reachable on %s", ctx.os.value)
        return None
    res = ctx.probes.run([exe, *_PS_ARGS, script])
    if res.is_err:
        _log.debug("AD3: powershell failed: %s", res.unwrap_err())
        return None
    run = res.unwrap()
    if run.exit_code != 0:
        _log.debug("AD3: powershell exit %s", run.exit_code)
        return None
    return [ln.strip() for ln in run.stdout_tail.splitlines() if ln.strip()]


def _sysfs_has_ad3(ctx: Ctx) -> bool | None:
    """Return whether sysfs lists the AD3, or None when /sys/bus/usb/devices is unreadable."""
    names = ctx.probes.listdir(SYSFS_USB)
    if names is None:
        return None
    for name in names:
        if ":" in name:
            continue
        vid = (ctx.probes.read_text(f"{SYSFS_USB}/{name}/idVendor") or "").strip().lower()
        pid = (ctx.probes.read_text(f"{SYSFS_USB}/{name}/idProduct") or "").strip().lower()
        if (vid, pid) == (AD3_VID, AD3_PID):
            return True
    return False


def usbipd_busid(ctx: Ctx) -> str | None:
    """Return the usbipd bus id of the AD3 (WSL only), or None when unknown."""
    exe = next((p for p in USBIPD_PATHS if bool(ctx.probes.which(p)) or ctx.probes.exists(p)), None)
    if exe is None:
        return None
    res = ctx.probes.run([exe, "list"])
    if res.is_err or res.unwrap().exit_code != 0:
        return None
    for line in res.unwrap().stdout_tail.splitlines():
        m = _USBIPD_LINE.match(line.strip())
        if m and m["vidpid"].lower() == f"{AD3_VID}:{AD3_PID}":
            return str(m["busid"])
    return None


def locate(ctx: Ctx) -> Ad3Where:
    """Find the AD3: in this side's own USB view, else (WSL only) on the Windows side."""
    side = side_of(ctx)
    if ctx.os is Os.WINDOWS:
        lines = _ps(ctx, PS_AD3)
        if lines is None:
            return Ad3Where(side, "unknown", reason="PowerShell Get-PnpDevice failed")
        return Ad3Where(side, "self" if lines else "none")
    seen = _sysfs_has_ad3(ctx)
    if seen is True:
        return Ad3Where(side, "self", busid=usbipd_busid(ctx) if ctx.os is Os.WSL else None)
    if seen is None and ctx.os is Os.LINUX:
        return Ad3Where(side, "unknown", reason="/sys/bus/usb/devices is not readable")
    if ctx.os is Os.WSL:
        lines = _ps(ctx, PS_AD3)
        if lines is None:
            return Ad3Where(side, "unknown", reason="powershell.exe is unavailable (interop off?)")
        if lines:
            return Ad3Where(side, "windows", busid=usbipd_busid(ctx))
    return Ad3Where(side, "none")


def _unless_present(ctx: Ctx, where: Ad3Where) -> Outcome | None:
    """Return the SKIP outcome when there is no AD3 to judge, else None."""
    if where.holder == "none":
        return skip(SkipReason.NO_DEVICE, f"[{where.side}] No Analog Discovery 3 found")
    if where.holder == "unknown":
        return skip(SkipReason.TOOL_MISSING, f"[{where.side}] {where.reason}")
    return None


@check(
    "AD3-010",
    Layer.AD3,
    "Analog Discovery 3 visible",
    Severity.WARNING,
    {"on-windows-side": "WSL: the AD3 is held by Windows, not attached to WSL"},
    "Linux/WSL: /sys/bus/usb/devices idVendor 1443 idProduct 7003; "
    "WSL also powershell.exe Get-PnpDevice VID_1443; Windows: Get-PnpDevice",
    applies_to=frozenset({Os.LINUX, Os.WSL, Os.WINDOWS}),
)
def ad3_010(ctx: Ctx) -> Outcome:
    """Find the AD3 and say which side holds it."""
    where = locate(ctx)
    if (none := _unless_present(ctx, where)) is not None:
        return none
    if where.holder == "windows":
        return warn(
            "on-windows-side",
            "[wsl] The AD3 is on the Windows side (not attached to WSL)",
            side=where.side,
            holder="windows",
            busid=where.busid,
        )
    holder = "attached to WSL via usbipd" if ctx.os is Os.WSL else "visible"
    return ok(f"[{where.side}] The AD3 is {holder}", side=where.side, holder="self")


@remedy("AD3-010", "on-windows-side")
def _ad3_010_windows(ctx: Ctx, out: Outcome) -> Fix:
    """Either drive the AD3 from Windows, or hand it to WSL with usbipd."""
    busid = str(out.facts.get("busid") or "<busid>")
    return Fix(
        "Pick one side for the AD3",
        (
            manual(
                "Easiest: leave the AD3 on Windows and run SADI's AD3 code with the "
                "Windows python.exe (WaveForms installs dwf.dll there).",
                "AD3-020 passes for the windows side.",
            ),
            action(
                "Or hand it to WSL (needs Linux libdwf too); in an Administrator PowerShell, "
                "bind it once.",
                "usbipd lists the device as Shared.",
                cmd(Os.WINDOWS, f"usbipd bind --busid {busid}"),
                mutates=Mutates.SYSTEM,
                changes="Marks the device as shareable with WSL; persists until unbound.",
            ),
            action(
                "Then attach it to WSL.",
                "usbipd lists the device as Attached.",
                cmd(
                    ctx.os,
                    f"usbipd{'.exe' if ctx.os is Os.WSL else ''} attach --wsl --busid {busid}",
                ),
                mutates=Mutates.SYSTEM,
                changes="Moves the device from Windows to WSL until it is unplugged.",
            ),
        ),
    )


def _lib_present(ctx: Ctx) -> str | None:
    """Return the first libdwf path that exists on Linux/WSL (env override, defaults, lib dirs)."""
    names = candidate_names("linux", ctx.probes.env(), None)
    for name in names:
        paths = [name] if os.path.isabs(name) else [f"{d}/{name}" for d in _LIB_DIRS]
        hit = next((p for p in paths if ctx.probes.exists(p)), None)
        if hit is not None:
            return hit
    return None


def _dll_present(ctx: Ctx) -> str | None:
    """Return the Windows dwf.dll path reachable from this side, if it exists."""
    override = ctx.probes.env().get(ENV_LIB_PATH)
    path = {Os.WINDOWS: DLL_WINDOWS, Os.WSL: DLL_VIA_WSL}.get(ctx.os)
    for cand in (override, path):
        if bool(cand) and ctx.probes.exists(cand):
            return cand
    return None


@check(
    "AD3-020",
    Layer.AD3,
    "WaveForms runtime library found",
    Severity.ERROR,
    {
        "no-libdwf": "libdwf.so is not installed on Linux/WSL",
        "wsl-use-windows": "WSL lacks libdwf but Windows has dwf.dll",
        "no-dwf-dll": "dwf.dll is missing on the Windows side",
    },
    "Linux/WSL: SADI_DWF_LIB or the sadi.bench.ad3 library names; "
    "Windows (and WSL via /mnt/c): C:\\Windows\\System32\\dwf.dll",
    applies_to=frozenset({Os.LINUX, Os.WSL, Os.WINDOWS}),
    depends_on=_DEPS,
)
def ad3_020(ctx: Ctx) -> Outcome:
    """Find the DWF runtime for the side that holds the device (the side in use)."""
    where = locate(ctx)
    if (none := _unless_present(ctx, where)) is not None:
        return none
    facts = {"side": where.side, "busid": where.busid}
    if ctx.os is Os.WINDOWS or where.holder == "windows":
        dll = _dll_present(ctx)
        if dll is None:
            return fail("no-dwf-dll", f"[windows] dwf.dll not found ({DLL_WINDOWS})", **facts)
        return ok(f"[windows] dwf.dll found at {dll}", **facts)
    lib = _lib_present(ctx)
    if lib is not None:
        return ok(f"[{where.side}] libdwf found at {lib}", **facts)
    if ctx.os is Os.WSL and ctx.probes.exists(DLL_VIA_WSL):
        return fail(
            "wsl-use-windows",
            "[wsl] No libdwf in WSL, but Windows has dwf.dll: drive the AD3 from Windows",
            **facts,
        )
    return fail("no-libdwf", f"[{where.side}] libdwf.so not found", **facts)


@remedy("AD3-020", "wsl-use-windows")
def _ad3_020_use_windows(ctx: Ctx, out: Outcome) -> Fix:
    """Headline: release the device from WSL and use Windows python; alternative: Linux packages."""
    busid = out.facts.get("busid")
    detach = (
        cmd(ctx.os, f"usbipd.exe detach --busid {busid}", fixable=ctx.os is Os.WSL)
        if bool(busid)
        else cmd(ctx.os, "usbipd.exe detach --busid <busid>")
    )
    return Fix(
        "Use the AD3 from Windows",
        (
            action(
                "Detach the AD3 from WSL so Windows owns it again (no Administrator needed).",
                "usbipd lists the device as Shared, not Attached.",
                detach,
                mutates=Mutates.SYSTEM,
                changes="Gives the device back to Windows until you attach it again.",
                alt="Instead, install the Linux packages: WaveForms (.deb) and the Digilent "
                "Adept runtime with `sudo apt install ./digilent.waveforms_*.deb` and "
                "`sudo apt install ./digilent.adept.runtime_*.deb`, then keep the AD3 attached to WSL.",
            ),
            action(
                "Run the AD3 code with the Windows Python, not WSL's.",
                "The Windows python prints the DWF version.",
                cmd(
                    Os.WINDOWS,
                    'python.exe -c "from sadi.bench.ad3.dll import load_backend; '
                    'print(load_backend().unwrap().version())"',
                ),
            ),
        ),
    )


def _deb_workaround_steps() -> tuple[Step, ...]:
    """Manual steps for when `apt install` of the WaveForms .deb fails (offline mirror, huge GUI deps)."""
    return (
        manual(
            "If `apt install` of the WaveForms .deb fails (offline or unreachable mirror, huge "
            "Qt/GUI dependencies), extract it instead: `dpkg-deb -x <path>/digilent.waveforms_*_amd64.deb "
            "~/.local/share/digilent-waveforms`, then "
            f"`export {ENV_LIB_PATH}=$HOME/.local/share/digilent-waveforms/usr/lib/libdwf.so`.",
            "The exported path points at an existing libdwf.so.",
        ),
        manual(
            "libdwf hardcodes /usr/share/digilent/waveforms/firmware, so copy it: "
            "`sudo mkdir -p /usr/share/digilent && sudo cp -r "
            "~/.local/share/digilent-waveforms/usr/share/digilent/waveforms /usr/share/digilent/`. "
            "Without it, open fails with 'Device not supported. No compatible configuration found'.",
            "/usr/share/digilent/waveforms/firmware exists.",
            mutates=Mutates.SYSTEM,
            changes="Copies firmware files under /usr/share/digilent (needs sudo).",
        ),
        manual(
            "The Adept runtime must also be installed; your shell needs the dialout group "
            "(relogin, or run via `sg dialout -c '<command>'`); always close the device before "
            "the process exits.",
            "AD3-040 passes with --ad3-open.",
        ),
    )


@remedy("AD3-020", "no-libdwf")
def _ad3_020_nolib(ctx: Ctx, out: Outcome) -> Fix:
    """Install the Linux WaveForms and Adept packages."""
    steps = [
        manual(
            "Download Digilent WaveForms (.deb) and the Adept runtime (.deb) from "
            "digilent.com and install them.",
            "libdwf.so exists under /usr/lib/digilent/waveforms.",
            mutates=Mutates.SYSTEM,
            changes="Installs system packages (needs sudo).",
        ),
        action(
            "Confirm the library is present.",
            "A path is printed.",
            cmd(ctx.os, "ls /usr/lib/digilent/waveforms/libdwf.so /usr/lib/libdwf.so"),
            if_not=f"Set {ENV_LIB_PATH} to the full path of libdwf.so.",
        ),
    ]
    steps.extend(_deb_workaround_steps())
    return Fix("Install the Linux WaveForms runtime", tuple(steps))


@remedy("AD3-020", "no-dwf-dll")
def _ad3_020_nodll(ctx: Ctx, out: Outcome) -> Fix:
    """Install WaveForms for Windows."""
    return Fix(
        "Install WaveForms for Windows",
        (
            manual(
                "Install Digilent WaveForms (it provides dwf.dll in System32) from "
                "digilent.com, then reopen the terminal.",
                f"{DLL_WINDOWS} exists.",
                mutates=Mutates.SYSTEM,
                changes="Installs the WaveForms application and runtime.",
            ),
            action(
                "Confirm the library is present.",
                "True is printed.",
                cmd(Os.WINDOWS, f"Test-Path {DLL_WINDOWS}"),
                if_not=f"Set {ENV_LIB_PATH} to the full path of dwf.dll.",
            ),
        ),
    )


@check(
    "AD3-030",
    Layer.AD3,
    "No WaveForms or Adept process holds the AD3",
    Severity.WARNING,
    {"held-by-process": "A WaveForms or Adept process is running and may hold the device"},
    "Windows/WSL: powershell.exe Get-Process WaveForms*,Adept*; Linux: pgrep -il waveforms",
    applies_to=frozenset({Os.LINUX, Os.WSL, Os.WINDOWS}),
    depends_on=_DEPS,
)
def ad3_030(ctx: Ctx) -> Outcome:
    """Warn when a WaveForms/Adept process is running next to the AD3."""
    where = locate(ctx)
    if (none := _unless_present(ctx, where)) is not None:
        return none
    if ctx.os is Os.LINUX:
        res = ctx.probes.run(_LINUX_PROCS)
        if res.is_err or res.unwrap().exit_code not in (0, 1):
            return skip(SkipReason.TOOL_MISSING, "[linux] pgrep is unavailable")
        names = [ln.strip() for ln in res.unwrap().stdout_tail.splitlines() if ln.strip()]
        proc_side = "linux"
    else:
        found = _ps(ctx, PS_PROCS)
        if found is None:
            return skip(SkipReason.TOOL_MISSING, f"[{where.side}] cannot list Windows processes")
        names = found
        proc_side = "windows"
    if names:
        return warn(
            "held-by-process",
            f"[{proc_side}] {', '.join(sorted(set(names)))} is running and may hold the AD3",
            side=proc_side,
            processes=sorted(set(names)),
        )
    return ok(f"[{proc_side}] No WaveForms or Adept process is running", side=proc_side)


@remedy("AD3-030", "held-by-process")
def _ad3_030_held(ctx: Ctx, out: Outcome) -> Fix:
    """Close the program that holds the device."""
    windows = out.facts.get("side") == "windows"
    listing = (
        cmd(Os.WINDOWS, "Get-Process WaveForms*,Adept*")
        if ctx.os is Os.WINDOWS
        else cmd(ctx.os, 'powershell.exe -NoProfile -Command "Get-Process WaveForms*,Adept*"')
        if windows
        else cmd(ctx.os, "pgrep -il waveforms")
    )
    return Fix(
        "Close WaveForms",
        (
            manual(
                "Close the WaveForms window (and any Adept utility); only one program can "
                "own the AD3 at a time.",
                "WaveForms is no longer in the taskbar.",
                mutates=Mutates.PROCESS,
                changes="Ends the program you close.",
            ),
            action(
                "Check that no process remains.",
                "Nothing is listed.",
                listing,
                if_not="End the remaining process from Task Manager (or `kill` on Linux).",
            ),
        ),
    )


@check(
    "AD3-040",
    Layer.AD3,
    "AD3 opens through the DWF library",
    Severity.ERROR,
    {"open-failed": "The library found the AD3 but could not open it"},
    "Only with --ad3-open: load the backend in a child, enumerate, open and close device 0",
    applies_to=frozenset({Os.LINUX, Os.WSL, Os.WINDOWS}),
    depends_on=("AD3-010", "AD3-020"),
    opt_in_flag="ad3_open",
)
def ad3_040(ctx: Ctx) -> Outcome:
    """Open the AD3 via the backend in a child process and close it again."""
    side = side_of(ctx)
    res = child_json(ctx, _OPEN_SCRIPT)
    if res.is_err:
        return skip(
            SkipReason.TOOL_MISSING, f"[{side}] open probe failed", detail=res.unwrap_err().detail
        )
    data = res.unwrap()
    status = data.get("status")
    detail = str(data.get("detail", ""))
    if status == "ok":
        return ok(f"[{side}] The AD3 opened and closed", side=side)
    if status == "no-device":
        return skip(SkipReason.NO_DEVICE, f"[{side}] The DWF library enumerates no device")
    if status == "no-library":
        return skip(SkipReason.TOOL_MISSING, f"[{side}] No DWF library to load", detail=detail)
    return fail("open-failed", f"[{side}] Opening the AD3 failed", detail=detail, side=side)


@remedy("AD3-040", "open-failed")
def _ad3_040_open(ctx: Ctx, out: Outcome) -> Fix:
    """Free the device, replug it, and retry."""
    wsl = (
        (
            manual(
                "WSL: detach and re-attach the AD3 with usbipd.exe, then re-run.",
                "usbipd lists the device as Attached.",
            ),
        )
        if ctx.os is Os.WSL
        else ()
    )
    deb = _deb_workaround_steps() if ctx.os is not Os.WINDOWS else ()
    return Fix(
        "Free the AD3",
        (
            manual(
                "Close WaveForms and any other program using the AD3, then unplug and replug it.",
                "The AD3 LED is on and AD3-030 passes.",
            ),
            *wsl,
            *deb,
        ),
    )


@check(
    "AD3-050",
    Layer.AD3,
    "SADI_DWF_LIB override points at a real file",
    Severity.WARNING,
    {"override-missing": "SADI_DWF_LIB is set but the file does not exist"},
    "Environment variable SADI_DWF_LIB, then an existence check of that path",
    applies_to=frozenset({Os.LINUX, Os.WSL, Os.WINDOWS}),
)
def ad3_050(ctx: Ctx) -> Outcome:
    """Warn when the library override names a path that is not there (it would be ignored)."""
    side = side_of(ctx)
    override = ctx.probes.env().get(ENV_LIB_PATH)
    if override is None or override == "":
        return ok(f"[{side}] {ENV_LIB_PATH} is not set (default discovery)", side=side)
    if ctx.probes.exists(override):
        return ok(f"[{side}] {ENV_LIB_PATH} points at {override}", side=side, path=override)
    return warn(
        "override-missing",
        f"[{side}] {ENV_LIB_PATH}={override} does not exist",
        side=side,
        path=override,
    )


@remedy("AD3-050", "override-missing")
def _ad3_050_override(ctx: Ctx, out: Outcome) -> Fix:
    """Fix or clear the override."""
    return Fix(
        "Repair the library override",
        (
            manual(
                f"Set {ENV_LIB_PATH} to the full path of an existing libdwf (dwf.dll on Windows), "
                f"or unset it to use default discovery (was {out.facts.get('path')}).",
                "The path exists and AD3-020 passes.",
            ),
        ),
    )


_LINUX_ACCESS = frozenset({Os.LINUX, Os.WSL})
FIRMWARE_DIR = "/usr/share/digilent/waveforms/firmware"


def _linux_ready(ctx: Ctx) -> Outcome | None:
    """Return a SKIP unless the AD3 is on this Linux/WSL side (windows-held devices are not ours)."""
    where = locate(ctx)
    if (none := _unless_present(ctx, where)) is not None:
        return none
    if where.holder == "windows":
        return skip(SkipReason.PREREQUISITE_FAILED, f"[{where.side}] The AD3 is held by Windows")
    return None


@check(
    "AD3-060",
    Layer.AD3,
    "User may access the AD3 USB device (dialout)",
    Severity.WARNING,
    {"no-dialout": "The user is not in the dialout group, so opening the AD3 may be denied"},
    "Linux/WSL: `id -nG` must list dialout",
    applies_to=_LINUX_ACCESS,
    depends_on=_DEPS,
)
def ad3_060(ctx: Ctx) -> Outcome:
    """Warn when the user lacks the dialout group the Adept runtime relies on."""
    if (none := _linux_ready(ctx)) is not None:
        return none
    side = side_of(ctx)
    res = ctx.probes.run(["id", "-nG"])
    if res.is_err or res.unwrap().exit_code != 0 or not res.unwrap().stdout_tail.strip():
        return skip(SkipReason.TOOL_MISSING, f"[{side}] cannot list the user's groups")
    groups = res.unwrap().stdout_tail.split()
    if "dialout" in groups:
        return ok(f"[{side}] The user is in the dialout group", side=side)
    return warn(
        "no-dialout", f"[{side}] The user is not in the dialout group", side=side, groups=groups
    )


@remedy("AD3-060", "no-dialout")
def _ad3_060_dialout(ctx: Ctx, out: Outcome) -> Fix:
    """Add the user to dialout (manual: needs sudo and a new login)."""
    return Fix(
        "Join the dialout group",
        (
            manual(
                "Run `sudo usermod -aG dialout $USER`, then log out and in again "
                "(or run commands via `sg dialout -c '<command>'`).",
                "`id -nG` lists dialout.",
                mutates=Mutates.SYSTEM,
                changes="Adds your account to the dialout group (needs sudo).",
            ),
        ),
    )


@check(
    "AD3-070",
    Layer.AD3,
    "WaveForms firmware directory installed",
    Severity.ERROR,
    {"no-firmware": f"{FIRMWARE_DIR} is missing, so the AD3 cannot be configured"},
    f"Linux/WSL: {FIRMWARE_DIR} exists (libdwf hardcodes this path)",
    applies_to=_LINUX_ACCESS,
    depends_on=("AD3-010", "AD3-020"),
)
def ad3_070(ctx: Ctx) -> Outcome:
    """Fail when the libdwf firmware directory is absent (open fails with 'no compatible configuration')."""
    if (none := _linux_ready(ctx)) is not None:
        return none
    side = side_of(ctx)
    if ctx.probes.exists(FIRMWARE_DIR):
        return ok(f"[{side}] Firmware directory present", side=side)
    return fail("no-firmware", f"[{side}] {FIRMWARE_DIR} is missing", side=side)


@remedy("AD3-070", "no-firmware")
def _ad3_070_firmware(ctx: Ctx, out: Outcome) -> Fix:
    """Install WaveForms properly, or copy the firmware directory out of the extracted package."""
    return Fix("Install the WaveForms firmware", _deb_workaround_steps())


_SESSION_SCRIPT = (
    "import json\n"
    "from sadi.bench.ad3 import Ad3Closed\n"
    "r = Ad3Closed.from_library()\n"
    "if r.is_err:\n"
    "    print(json.dumps({'status': 'no-library', 'detail': str(r.unwrap_err().detail)}))\n"
    "    raise SystemExit(0)\n"
    "c = r.unwrap()\n"
    "e = c.enumerate()\n"
    "if e.is_err or not e.unwrap():\n"
    "    print(json.dumps({'status': 'no-device', 'detail': ''}))\n"
    "    raise SystemExit(0)\n"
    "o = c.open()\n"
    "if o.is_err:\n"
    "    print(json.dumps({'status': 'session-failed', 'detail': o.unwrap_err().hint}))\n"
    "    raise SystemExit(0)\n"
    "s = o.unwrap()\n"
    "v = s.version()\n"
    "s.close()\n"
    "if v.is_err:\n"
    "    print(json.dumps({'status': 'session-failed', 'detail': v.unwrap_err().hint}))\n"
    "else:\n"
    "    print(json.dumps({'status': 'ok', 'detail': v.unwrap()}))\n"
)


@check(
    "AD3-080",
    Layer.AD3,
    "AD3 wrapper session opens, reads the version and closes",
    Severity.ERROR,
    {"session-failed": "The high-level Ad3Session could not open or query the AD3"},
    "Only with --ad3-open: sadi.bench.ad3.Ad3Closed.open() in a child, version(), close()",
    applies_to=frozenset({Os.LINUX, Os.WSL, Os.WINDOWS}),
    depends_on=("AD3-010", "AD3-020", "AD3-040"),
    opt_in_flag="ad3_open",
)
def ad3_080(ctx: Ctx) -> Outcome:
    """Exercise the typestate wrapper end to end in a child process."""
    side = side_of(ctx)
    res = child_json(ctx, _SESSION_SCRIPT)
    if res.is_err:
        return skip(
            SkipReason.TOOL_MISSING,
            f"[{side}] session probe failed",
            detail=res.unwrap_err().detail,
        )
    data = res.unwrap()
    status = data.get("status")
    detail = str(data.get("detail", ""))
    if status == "ok":
        return ok(f"[{side}] The AD3 session works (DWF {detail})", side=side, version=detail)
    if status == "no-device":
        return skip(SkipReason.NO_DEVICE, f"[{side}] The DWF library enumerates no device")
    if status == "no-library":
        return skip(SkipReason.TOOL_MISSING, f"[{side}] No DWF library to load", detail=detail)
    return fail("session-failed", f"[{side}] The AD3 session failed", detail=detail, side=side)


@remedy("AD3-080", "session-failed")
def _ad3_080_session(ctx: Ctx, out: Outcome) -> Fix:
    """Read the numbered hint in the detail and free the device."""
    return Fix(
        "Fix the AD3 session",
        (
            manual(
                "Follow the numbered hint shown in the failure detail; it is specific to the "
                "error code (busy, device lost, not supported, ...).",
                "AD3-080 passes with --ad3-open.",
            ),
            manual(
                "Close WaveForms and other SADI processes, then unplug and replug the AD3.",
                "AD3-030 passes.",
            ),
        ),
    )
