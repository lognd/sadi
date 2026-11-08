"""DEV checks: talk to the attached board (open, query, state, stream, reset).

Without a board every check ends in a SKIP with reason `no-device` rather than
a failure: a lab machine with nothing plugged in is not broken. Everything is
read-only; the only writes are protocol commands to the board, and Reset is
opt-in (`--with-reset`).
"""

# frob:ticket 01M6WJHVRVS94M67F41C3P2BMG
from __future__ import annotations

from sadi.doctor.devprobe import (
    BOOT_SLOW_S,
    MIN_PACKETS_PER_S,
    DeviceFacts,
)
from sadi.doctor.registry import Ctx, Fix, Outcome, check, fail, ok, remedy, skip, warn
from sadi.doctor.schema import Layer, Mutates, Os, Severity, SkipReason
from sadi.doctor.steps import action, cmd, manual

KNOWN_FIRMWARE = (1.003, 3.41)
_USB_DEPS = ("USB-040", "USB-050")
_DEV_DEPS = ("DEV-010",)
_NO_BOARD = "No board is attached, so there is nothing to talk to"

_LIST_PORTS = {
    Os.LINUX: "ls -l /dev/ttyUSB* /dev/ttyACM*",
    Os.WSL: "ls -l /dev/ttyUSB* /dev/ttyACM*",
    Os.MACOS: "ls -l /dev/cu.usb*",
    Os.WINDOWS: "Get-CimInstance Win32_SerialPort | Select-Object DeviceID, Description",
}


def device(ctx: Ctx) -> DeviceFacts:
    """Return the board survey for this run's options."""
    o = ctx.options
    return ctx.probes.device_facts(o.port, o.stream_seconds, o.with_reset)


def _no_device(facts: DeviceFacts) -> Outcome | None:
    """Return the informational skip when no board could be reached, else None."""
    if facts.open_status == "no-device":
        return skip(
            SkipReason.NO_DEVICE, _NO_BOARD, detail=facts.open_detail, ports=list(facts.ports)
        )
    return None


def _port(out: Outcome, ctx: Ctx) -> str:
    """Name the port a remedy should talk about."""
    default = {Os.WINDOWS: "COM3", Os.MACOS: "/dev/cu.usbserial-0001"}.get(ctx.os, "/dev/ttyUSB0")
    return str(out.facts.get("port") or default)


def _list_ports_step(ctx: Ctx):  # noqa: ANN202 - Step type is internal to steps
    """Build the step that lists serial ports on this OS."""
    return action(
        "List the serial ports the OS exposes.",
        "Your board's port is listed (a ttyUSB, cu.usbserial or COM entry).",
        cmd(ctx.os, _LIST_PORTS[ctx.os]),
        if_not="The board is not enumerated; fix the USB checks (USB-020 to USB-050) first.",
    )


def _power_cycle_step():  # noqa: ANN202 - Step type is internal to steps
    """Build the manual power-cycle step."""
    return manual(
        "Unplug the board's USB cable, wait 5 seconds, plug it back in.",
        "The board's power LED lights within a few seconds.",
        mutates=Mutates.PROCESS,
        changes="Power-cycles the board; any run in progress on it is lost.",
    )


@check(
    "DEV-010",
    Layer.DEV,
    "Serial port opens",
    Severity.ERROR,
    {
        "open-denied": "The OS refused to open the port (permission)",
        "open-busy": "Another program holds the port open",
        "open-io-error": "The port failed to open for another reason",
    },
    "sadi_py.open_serial on the first FTDI port (or --port) with a query-only handshake",
    depends_on=_USB_DEPS,
)
def dev_010(ctx: Ctx) -> Outcome:
    """Open the serial port and close it again."""
    facts = device(ctx)
    if (none := _no_device(facts)) is not None:
        return none
    if facts.open_status == "ok":
        return ok(f"Opened {facts.port}", port=facts.port)
    mode = {"denied": "open-denied", "busy": "open-busy"}.get(facts.open_status, "open-io-error")
    return fail(mode, f"Could not open {facts.port}", port=facts.port, detail=facts.open_detail)


@remedy("DEV-010", "open-denied")
def _dev_010_denied(ctx: Ctx, out: Outcome) -> Fix:
    """Fix serial port permission per OS."""
    port = _port(out, ctx)
    if ctx.os in (Os.LINUX, Os.WSL):
        steps = (
            action(
                "Show who may open the port and which groups you are in.",
                "The port's group (usually dialout) appears in your `id` output.",
                cmd(ctx.os, f"ls -l {port}; id"),
                if_not="If the group is missing, continue with the next step.",
            ),
            action(
                "Add your user to the port's group.",
                "No output.",
                cmd(ctx.os, "sudo usermod -aG dialout $USER"),
                mutates=Mutates.SYSTEM,
                changes="Adds your account to the dialout group.",
            ),
            manual(
                "Log out and in again (WSL: run `wsl --shutdown` in PowerShell, then reopen).",
                "`id` lists dialout.",
            ),
        )
    elif ctx.os is Os.MACOS:
        steps = (
            action(
                "Show the port's owner and mode.",
                "The port is readable and writable by your user.",
                cmd(ctx.os, f"ls -l {port}"),
                if_not="Use the /dev/cu.* node, not /dev/tty.*, and replug the board.",
            ),
            manual(
                "If macOS asked to allow the USB accessory, open System Settings, "
                "Privacy & Security and allow it, then replug the board.",
                "The port opens without a permission error.",
            ),
        )
    else:
        steps = (
            manual(
                "Close any program that talks to the board (terminal emulators, vendor tools) "
                "and run PowerShell as the same user that runs SADI.",
                "No other program lists the port as in use.",
            ),
            action(
                "Check Windows still sees the port and it is not disabled.",
                "The port is listed with status OK.",
                cmd(ctx.os, _LIST_PORTS[ctx.os]),
                if_not="Open Device Manager, enable the port, or reinstall the FTDI driver.",
            ),
        )
    return Fix("Get permission to open the serial port", steps)


@remedy("DEV-010", "open-busy")
def _dev_010_busy(ctx: Ctx, out: Outcome) -> Fix:
    """Find and close whatever holds the port."""
    port = _port(out, ctx)
    if ctx.os is Os.WINDOWS:
        find = manual(
            "Close other SADI windows, serial terminals and vendor tools; "
            "Resource Monitor (Associated Handles, search 'COM') names the holder.",
            "No other program has the port open.",
        )
    else:
        find = action(
            "Find the process that has the port open.",
            "A process name and pid are listed (no output means nothing holds it).",
            cmd(ctx.os, f"lsof {port}"),
            alt=None if ctx.os is Os.MACOS else f"fuser -v {port}",
            if_not="Nothing listed: the lock may be stale; unplug and replug the board.",
        )
    stop = manual(
        "Close that program, or stop the other SADI session (press Stop, then quit it).",
        "The holder is gone.",
        mutates=Mutates.PROCESS,
        changes="Ends the other program's use of the board.",
    )
    return Fix("Free the serial port", (find, stop))


@remedy("DEV-010", "open-io-error")
def _dev_010_io(ctx: Ctx, out: Outcome) -> Fix:
    """Re-seat the board and re-list ports."""
    return Fix(
        "Re-seat the board and look for a kernel or driver error",
        (
            _list_ports_step(ctx),
            _power_cycle_step(),
            action(
                "Read the recent USB messages for errors about the board."
                if ctx.os in (Os.LINUX, Os.WSL)
                else "Check the port is still listed after the replug.",
                "No 'error' or 'disconnect' lines about the board.",
                cmd(
                    ctx.os,
                    {
                        Os.LINUX: "dmesg | tail -n 30",
                        Os.WSL: "dmesg | tail -n 30",
                        Os.MACOS: "log show --last 2m --predicate 'subsystem contains \"usb\"'",
                        Os.WINDOWS: _LIST_PORTS[Os.WINDOWS],
                    }[ctx.os],
                ),
                if_not="Try another USB port or cable, without a hub.",
            ),
        ),
    )


def _fw_known(version: str) -> bool:
    """True when the firmware version string matches a known release."""
    try:
        return any(abs(float(version) - k) < 0.0005 for k in KNOWN_FIRMWARE)
    except ValueError:
        return False


@check(
    "DEV-020",
    Layer.DEV,
    "Board answers a query",
    Severity.ERROR,
    {
        "no-reply": "The board is silent",
        "garbage-reply": "Bytes arrive but they are not a valid reply",
        "unexpected-firmware": "The board runs a firmware this SADI has not been tested with",
    },
    "Query over a query-only handshake; records the firmware version and state byte",
    depends_on=_DEV_DEPS,
)
def dev_020(ctx: Ctx) -> Outcome:
    """Ask the board for its firmware version."""
    facts = device(ctx)
    if (none := _no_device(facts)) is not None:
        return none
    if facts.open_status != "ok":
        return skip(SkipReason.PREREQUISITE_FAILED, "The port did not open (see DEV-010)")
    if facts.query_status == "no-reply":
        return fail(
            "no-reply", "The board did not answer", port=facts.port, detail=facts.stream_detail
        )
    if facts.query_status == "garbage":
        return fail(
            "garbage-reply",
            "The board sent bytes that are not a valid reply",
            port=facts.port,
            reply_hex=facts.reply_hex[:128],
            detail=facts.stream_detail,
        )
    if not _fw_known(facts.fw_version):
        return warn(
            "unexpected-firmware",
            f"Firmware {facts.fw_version} is not 1.003 or 3.41",
            firmware=facts.fw_version,
        )
    return ok(f"Board answered, firmware {facts.fw_version}", firmware=facts.fw_version)


@remedy("DEV-020", "no-reply")
def _dev_020_silent(ctx: Ctx, out: Outcome) -> Fix:
    """Walk through power, channel and port selection."""
    return Fix(
        "Get the board to answer",
        (
            manual(
                "Check the board is powered (power LED on) and its USB cable is firmly seated.",
                "The power LED is lit.",
            ),
            manual(
                "On a multi-channel board, confirm the channel selector matches the channel "
                "SADI is wired to.",
                "The selector points at the connected channel.",
            ),
            _list_ports_step(ctx),
            _power_cycle_step(),
        ),
    )


@remedy("DEV-020", "garbage-reply")
def _dev_020_garbage(ctx: Ctx, out: Outcome) -> Fix:
    """Point at the wrong-device or wrong-baud cause."""
    return Fix(
        "Make sure SADI is talking to the board and not another serial device",
        (
            _list_ports_step(ctx),
            manual(
                "Unplug every other USB serial device, then pass the board's port explicitly "
                "with `--port`.",
                "Only the board's port remains in the listing.",
            ),
            manual(
                "If the output keeps being garbled, the board may be running different firmware "
                "or be a different device; note the hex shown in the report and ask the lab.",
                "The query is answered.",
            ),
        ),
    )


@remedy("DEV-020", "unexpected-firmware")
def _dev_020_firmware(ctx: Ctx, out: Outcome) -> Fix:
    """Explain the untested firmware; nothing to change."""
    return Fix(
        "Confirm the firmware version",
        (
            manual(
                f"This SADI was tested with firmware 1.003 and 3.41; the board reports "
                f"{out.facts.get('firmware')}. Ask the lab whether that build is intended.",
                "You know whether the board should run this firmware.",
                if_not="If it is wrong, reflash the board with the lab's firmware tool.",
            ),
        ),
    )


@check(
    "DEV-030",
    Layer.DEV,
    "Board state is sane",
    Severity.WARNING,
    {
        "streaming-unattended": "The board is streaming with no SADI process attached",
        "unknown-state": "The board reports a state byte SADI does not know",
    },
    "State byte from the query: Booted (1), Stopped (2) or Streaming (3)",
    depends_on=_DEV_DEPS,
)
def dev_030(ctx: Ctx) -> Outcome:
    """Judge the state byte the board reported."""
    facts = device(ctx)
    if (none := _no_device(facts)) is not None:
        return none
    if facts.query_status != "ok":
        return skip(SkipReason.PREREQUISITE_FAILED, "The board did not answer (see DEV-020)")
    if facts.state == "running":
        return warn(
            "streaming-unattended",
            "The board is streaming but SADI is not running it",
            state_byte=facts.state_byte,
        )
    if facts.state not in ("booted", "stopped"):
        return warn(
            "unknown-state",
            f"Unknown state byte {facts.state_byte}",
            state_byte=facts.state_byte,
        )
    return ok(f"Board is {facts.state}", state=facts.state, state_byte=facts.state_byte)


@remedy("DEV-030", "streaming-unattended")
def _dev_030_streaming(ctx: Ctx, out: Outcome) -> Fix:
    """Stop the orphaned stream or power-cycle."""
    return Fix(
        "Stop the unattended stream",
        (
            manual(
                "Start SADI, connect to the board and press Stop.",
                "SADI reports the board is stopped.",
                mutates=Mutates.PROCESS,
                changes="Sends Stop to the board.",
                if_not="Otherwise power-cycle the board in the next step.",
            ),
            _power_cycle_step(),
        ),
    )


@remedy("DEV-030", "unknown-state")
def _dev_030_unknown(ctx: Ctx, out: Outcome) -> Fix:
    """Power-cycle and re-query."""
    return Fix("Power-cycle the board", (_power_cycle_step(),))


@check(
    "DEV-040",
    Layer.DEV,
    "Short stream is healthy",
    Severity.WARNING,
    {
        "low-rate": "Fewer than 900 packets per second arrive",
        "gaps": "Packets were missed during the stream",
        "saturated-channel": "A channel sits at the converter's limit",
        "stop-not-acked": "The board did not acknowledge Stop",
    },
    "Only with --stream-seconds N: Start, read N seconds, Stop; rate, gaps, saturation",
    depends_on=_DEV_DEPS,
    opt_in_flag="stream_seconds",
)
def dev_040(ctx: Ctx) -> Outcome:
    """Stream briefly and judge rate, gaps, saturation and the Stop acknowledgement."""
    facts = device(ctx)
    if (none := _no_device(facts)) is not None:
        return none
    if facts.stream_status != "ok":
        return skip(
            SkipReason.PREREQUISITE_FAILED,
            "The stream did not run (state or error)",
            detail=facts.stream_detail,
        )
    rate = round(facts.packets_per_s, 1)
    if not facts.stop_acked:
        return fail("stop-not-acked", "The board did not acknowledge Stop", rate=rate)
    if facts.packets_per_s < MIN_PACKETS_PER_S:
        return warn("low-rate", f"Only {rate} packets per second", rate=rate)
    if facts.gap_events or facts.dropped_bytes:
        return warn(
            "gaps",
            f"{facts.gap_events} gaps, {facts.dropped_bytes} dropped bytes",
            gaps=facts.gap_events,
            dropped=facts.dropped_bytes,
        )
    if facts.saturated_channels:
        return warn(
            "saturated-channel",
            f"Channels {list(facts.saturated_channels)} are at the converter limit",
            channels=[str(c) for c in facts.saturated_channels],
        )
    return ok(f"{rate} packets per second, no gaps", rate=rate)


@remedy("DEV-040", "low-rate")
def _dev_040_rate(ctx: Ctx, out: Outcome) -> Fix:
    """Remove USB bandwidth and latency bottlenecks."""
    wsl = (
        (
            manual(
                "WSL: usbip adds latency; if you can, run SADI natively on Windows instead.",
                "The rate rises, or you know usbip is the limit.",
            ),
        )
        if ctx.os is Os.WSL
        else ()
    )
    return Fix(
        "Raise the packet rate",
        (
            manual(
                "Plug the board straight into the computer, not through a hub, and close "
                "heavy programs.",
                "Re-running with --stream-seconds shows 900 packets per second or more.",
            ),
            *wsl,
        ),
    )


@remedy("DEV-040", "gaps")
def _dev_040_gaps(ctx: Ctx, out: Outcome) -> Fix:
    """Reduce load and re-try with a better cable."""
    return Fix(
        "Stop packets going missing",
        (
            manual(
                "Use a short, good USB cable on a port without a hub; avoid running other "
                "heavy work while recording.",
                "A repeat run reports no gaps.",
            ),
        ),
    )


@remedy("DEV-040", "saturated-channel")
def _dev_040_saturated(ctx: Ctx, out: Outcome) -> Fix:
    """Check the sensor wiring for the saturated channel."""
    return Fix(
        "Check the sensor on the saturated channel",
        (
            manual(
                f"Channels {out.facts.get('channels')} read the converter's limit: check the "
                "sensor is connected and within range (an LVDT at its end stop looks like this).",
                "The channel reads inside its range.",
            ),
        ),
    )


@remedy("DEV-040", "stop-not-acked")
def _dev_040_stop(ctx: Ctx, out: Outcome) -> Fix:
    """Recover a board that ignored Stop."""
    return Fix(
        "Recover the board",
        (
            _power_cycle_step(),
            manual(
                "Re-run with --stream-seconds; if Stop is still not acknowledged, "
                "record the firmware version from DEV-020 and report it to the lab.",
                "Stop is acknowledged.",
            ),
        ),
    )


@check(
    "DEV-050",
    Layer.DEV,
    "Reset and boot time",
    Severity.INFO,
    {
        "boot-timeout": "The board did not reply after Reset",
        "boot-slow": "The board took a long time to reply after Reset",
    },
    "Only with --with-reset: Reset, time the first reply (reports only, unverified on hardware)",
    depends_on=_DEV_DEPS,
    opt_in_flag="with_reset",
)
def dev_050(ctx: Ctx) -> Outcome:
    """Reset the board and time how long it takes to answer."""
    facts = device(ctx)
    if (none := _no_device(facts)) is not None:
        return none
    if facts.boot_status == "not-run":
        return skip(SkipReason.PREREQUISITE_FAILED, "Reset did not run (port or query failed)")
    secs = round(facts.boot_seconds, 2)
    if facts.boot_status == "timeout":
        return fail("boot-timeout", f"No reply {secs} s after Reset", seconds=secs)
    if facts.boot_seconds > BOOT_SLOW_S:
        return warn("boot-slow", f"The board needed {secs} s to answer", seconds=secs)
    return ok(f"The board answered {secs} s after Reset", seconds=secs)


@remedy("DEV-050", "boot-timeout")
def _dev_050_timeout(ctx: Ctx, out: Outcome) -> Fix:
    """Power-cycle after a Reset that never came back."""
    return Fix(
        "Bring the board back after Reset",
        (
            _power_cycle_step(),
            action(
                "Query the board again.",
                "The board answers (DEV-020 passes).",
                cmd(ctx.os, "sadi-doctor --check DEV-020"),
            ),
        ),
    )


@remedy("DEV-050", "boot-slow")
def _dev_050_slow(ctx: Ctx, out: Outcome) -> Fix:
    """Note the slow boot; nothing to change."""
    return Fix(
        "Note the boot time",
        (
            manual(
                f"Boot took {out.facts.get('seconds')} s. This is informational until boot "
                "timing is verified on hardware; no action is needed.",
                "You have recorded the figure.",
            ),
        ),
    )
