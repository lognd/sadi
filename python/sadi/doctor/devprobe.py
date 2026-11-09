"""Read-only device and simulator surveys: the facts the DEV and SIM checks judge.

sadi_py is imported lazily so the doctor works (and degrades to a clear
informational result) on a machine without the native binding or a board.
"""

# frob:ticket 01M6WJHVRVS94M67F41C3P2BMG
# frob:ticket 01M6Z1VM8TA5ZF8F05QG0ZFJH3
from __future__ import annotations

import time
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from sadi.logging_setup import get_logger

_log = get_logger(__name__)

FTDI_VID = 0x0403
SCENARIO_NAMES = ("clean", "noisy", "drifting", "creeping", "slipping", "saturating", "combined")
SIM_PACKETS = 100
MIN_PACKETS_PER_S = 900.0
BOOT_TIMEOUT_S = 10.0
BOOT_SLOW_S = 3.0
FULL_SCALE = (0, 0xFFFF)

OpenStatus = Literal["ok", "no-device", "denied", "busy", "io-error"]
QueryStatus = Literal["not-run", "ok", "no-reply", "garbage"]
StreamStatus = Literal["not-run", "ok", "error"]
BootStatus = Literal["not-run", "ok", "timeout"]


class DeviceFacts(BaseModel):
    """What one read-only session against the attached board observed."""

    model_config = ConfigDict(frozen=True)
    ports: tuple[str, ...] = ()
    port: str | None = None
    port_results: tuple[str, ...] = ()
    open_status: OpenStatus = "no-device"
    open_detail: str = ""
    query_status: QueryStatus = "not-run"
    reply_hex: str = ""
    fw_version: str = ""
    state: str = ""
    state_byte: int | None = None
    stream_status: StreamStatus = "not-run"
    packets_per_s: float = 0.0
    gap_events: int = 0
    dropped_bytes: int = 0
    saturated_channels: tuple[int, ...] = ()
    stop_acked: bool = True
    stream_detail: str = ""
    boot_status: BootStatus = "not-run"
    boot_seconds: float = 0.0


class SimFacts(BaseModel):
    """What the simulator session and the scenario sweep observed."""

    model_config = ConfigDict(frozen=True)
    binding_ok: bool = True
    connect_ok: bool = True
    timed_out: bool = False
    data_ok: bool = True
    detail: str = ""
    packets: int = 0
    failed_scenarios: tuple[str, ...] = ()


def _classify_open(detail: str) -> OpenStatus:
    """Map an open error's text to denied, busy or io-error."""
    low = detail.lower()
    if "permission" in low or "denied" in low or "access" in low:
        return "denied"
    if "busy" in low or "in use" in low or "locked" in low:
        return "busy"
    return "io-error"


def _pick_ports(sp: Any, wanted: str | None) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return (all port names, ports to try): the requested one, else every FTDI port sorted.

    An FT2232 exposes two serial ports (channels A and B); SADI sits on only one.
    """
    infos = sp.ports()
    names: tuple[str, ...] = tuple(str(p.name) for p in infos)
    if wanted is not None:
        return names, (wanted,)
    return names, tuple(sorted(str(p.name) for p in infos if p.vid == FTDI_VID))


def _query_port(sp: Any, port: str, cfg: Any) -> tuple[Any, dict[str, object]]:
    """Open `port` and query it; return (session or None, facts so far). Read-only."""
    try:
        sess = sp.open_serial(port, cfg)
    except Exception as exc:  # noqa: BLE001 - classified by text below
        detail = getattr(exc, "detail", str(exc))
        _log.info("open %s failed: %s", port, detail)
        return None, {
            "port": port,
            "open_status": _classify_open(detail),
            "open_detail": detail,
        }
    facts: dict[str, object] = {"port": port, "open_status": "ok"}
    try:
        sess.connect()
        info = sess.query()
    except Exception as exc:  # noqa: BLE001 - no reply vs garbage by error kind
        garbage = type(exc).__name__ == "CodecFailure"
        facts["query_status"] = "garbage" if garbage else "no-reply"
        facts["stream_detail"] = getattr(exc, "detail", str(exc))
        _close(sess)
        return None, facts
    facts.update(
        query_status="ok",
        fw_version=f"{info.fw_version:.3f}",
        state=_state_name(info.state),
        state_byte=info.state_byte,
    )
    return sess, facts


def _state_name(state: Any) -> str:
    """Lower-case name of a DeviceState; the native enum has no `.name`, so parse its str."""
    return str(getattr(state, "name", None) or str(state).rsplit(".", 1)[-1]).lower()


def _close(sess: Any) -> None:
    """Close a session, best effort."""
    try:
        sess.close()
    except Exception as exc:  # noqa: BLE001 - closing is best effort
        _log.warning("close failed: %s", exc)


def _summarize(facts: dict[str, object]) -> str:
    """One line saying what a probed port did, for the per-port diagnosis."""
    port = facts["port"]
    if facts["open_status"] != "ok":
        return f"{port}: did not open ({facts['open_status']}: {facts.get('open_detail', '')})"
    status = facts.get("query_status")
    if status == "ok":
        return f"{port}: answered, firmware {facts['fw_version']}"
    if status == "garbage":
        return f"{port}: bytes arrived but no valid reply ({facts.get('stream_detail', '')})"
    return f"{port}: silent ({facts.get('stream_detail', '')})"


def _stream(sp: Any, sess: Any, seconds: int) -> dict[str, object]:
    """Start, read for `seconds`, stop; return the DEV-040 facts as a dict."""
    packets = gaps = dropped = 0
    lo = [False] * 4
    hi = [False] * 4
    started = time.monotonic()
    sess.start(sp.AdcMode.IDEAL)
    try:
        while time.monotonic() - started < seconds:
            blk = sess.read_block()
            packets += len(blk.msg_count)
            gaps += blk.gap_events
            dropped += blk.dropped_bytes
            if blk.n_samples:
                for ch in range(4):
                    col = blk.adc_raw[:, ch]
                    lo[ch] = lo[ch] or bool((col == FULL_SCALE[0]).all())
                    hi[ch] = hi[ch] or bool((col == FULL_SCALE[1]).all())
    finally:
        elapsed = max(time.monotonic() - started, 1e-9)
    acked = True
    try:
        sess.stop()
    except Exception as exc:  # noqa: BLE001 - any stop failure means no ack
        _log.warning("stop not acknowledged: %s", exc)
        acked = False
    return {
        "stream_status": "ok",
        "packets_per_s": packets / elapsed,
        "gap_events": gaps,
        "dropped_bytes": dropped,
        "saturated_channels": tuple(i for i in range(4) if lo[i] or hi[i]),
        "stop_acked": acked,
    }


def _reset(sess: Any) -> dict[str, object]:
    """Reset the board and time the first reply."""
    t0 = time.monotonic()
    try:
        sess.reset()
    except Exception as exc:  # noqa: BLE001 - any failure to reply is a boot timeout
        _log.warning("no reply after reset: %s", exc)
        return {"boot_status": "timeout", "boot_seconds": time.monotonic() - t0}
    dt = time.monotonic() - t0
    return {"boot_status": "timeout" if dt > BOOT_TIMEOUT_S else "ok", "boot_seconds": dt}


def probe_device(port: str | None, stream_seconds: int, with_reset: bool) -> DeviceFacts:
    """Open the board, query it and optionally stream or reset; never raises, never writes data.

    With no explicit port every FTDI port is tried in order (an FT2232 has two channels, only
    one wired to SADI); the first that answers is used and each port's outcome is recorded.
    """
    try:
        import sadi_py as sp
    except ImportError as exc:
        return DeviceFacts(open_status="no-device", open_detail=f"sadi_py not importable: {exc}")
    try:
        names, candidates = _pick_ports(sp, port)
    except Exception as exc:  # noqa: BLE001 - enumeration failure degrades to no device
        _log.warning("port enumeration failed: %s", exc)
        return DeviceFacts(open_status="no-device", open_detail=f"port listing failed: {exc}")
    if not candidates:
        return DeviceFacts(ports=names, open_status="no-device", open_detail="no serial port")
    cfg = sp.SessionConfig(handshake=sp.Handshake.QUERY_ONLY)
    results: list[str] = []
    sess: Any = None
    facts: dict[str, object] = {}
    for cand in candidates:
        sess, facts = _query_port(sp, cand, cfg)
        results.append(_summarize(facts))
        _log.info("probe %s: %s", cand, results[-1])
        if sess is not None:
            break
    facts.update(ports=names, port_results=tuple(results))
    if sess is None:
        return DeviceFacts.model_validate(facts)
    try:
        if stream_seconds > 0 and facts["state"] != "running":
            try:
                facts.update(_stream(sp, sess, stream_seconds))
            except Exception as exc:  # noqa: BLE001 - stream failure is a fact, not a crash
                facts.update(stream_status="error", stream_detail=str(exc))
        if with_reset:
            facts.update(_reset(sess))
    finally:
        _close(sess)
    return DeviceFacts.model_validate(facts)


def probe_sim() -> SimFacts:
    """Run the clean scenario's connect sequence and construct every scenario."""
    try:
        import sadi_py as sp
    except ImportError as exc:
        return SimFacts(binding_ok=False, connect_ok=False, detail=f"sadi_py not importable: {exc}")
    failed = []
    for name in SCENARIO_NAMES:
        try:
            sp.open_sim(name, 1).close()
        except Exception as exc:  # noqa: BLE001 - recorded per scenario
            _log.warning("scenario %s failed to load: %s", name, exc)
            failed.append(name)
    base = SimFacts(failed_scenarios=tuple(failed))
    try:
        sess = sp.open_sim("clean", 1)
        sess.connect()
        sess.start(sp.AdcMode.IDEAL)
    except Exception as exc:  # noqa: BLE001 - connect failure is a fact
        return base.model_copy(update={"connect_ok": False, "detail": str(exc)})
    packets, counts, vals = 0, [], []
    try:
        while packets < SIM_PACKETS:
            blk = sess.read_block()
            packets += len(blk.msg_count)
            counts.extend(int(c) for c in blk.msg_count)
            vals.append(blk.volts)
        sess.stop()
    except Exception as exc:  # noqa: BLE001 - a read timeout is its own mode
        timed_out = type(exc).__name__ in {"ReadTimeoutError", "CommandTimeoutError"}
        return base.model_copy(
            update={"connect_ok": not timed_out, "timed_out": timed_out, "detail": str(exc)}
        )
    finally:
        sess.close()
    import numpy as np

    volts = np.concatenate(vals)
    steps = [b - a for a, b in zip(counts, counts[1:], strict=False)]
    data_ok = bool(np.isfinite(volts).all()) and all(s == 1 for s in steps)
    detail = "" if data_ok else "msgCount discontinuity or non-finite volts"
    return base.model_copy(update={"packets": packets, "data_ok": data_ok, "detail": detail})
