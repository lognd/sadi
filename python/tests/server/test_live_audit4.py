"""Audit-4 L1/L2/L6: idle hint wording, resume with no device, SETTINGS firmware."""

# frob:ticket 01M72964B6QESNJ271PXD2H2RQ
from __future__ import annotations

from sadi.core.device import DeviceService, DeviceSource
from sadi.core.errors import DeviceCode
from sadi.core.pipeline import Bus
from sadi.server.live import (
    _CAPTURE_STOP_HINTS,
    STOP_IDLE,
    LiveAcquisition,
    LiveError,
)


def _live() -> tuple[DeviceService, LiveAcquisition]:
    dev = DeviceService(DeviceSource(kind="sim", manual_load=True))  # never opened
    return dev, LiveAcquisition(dev, Bus(), watch_poll_s=3600.0)


# frob:tests python/sadi/server/live.py::LiveAcquisition.capture_block_hint
def test_idle_hint_points_at_resume() -> None:
    """The idle hint names Resume live readings, not Mark load change."""
    hint = _CAPTURE_STOP_HINTS[STOP_IDLE]
    assert "Resume live readings" in hint and "Mark load change" not in hint


# frob:tests python/sadi/core/device.py::DeviceService.start_streaming
def test_start_streaming_unopened_is_err_not_raise() -> None:
    """An unopened service returns a NOT_FOUND error instead of raising."""
    dev, _live_acq = _live()
    res = dev.start_streaming()
    assert res.is_err and res.danger_err.code == DeviceCode.NOT_FOUND


# frob:tests python/sadi/server/live.py::LiveAcquisition._resume_after_idle_locked
def test_resume_after_idle_without_device_is_no_device() -> None:
    """A detached device gives NoDevice from the idle resume, never a 500."""
    _dev, live = _live()
    live._writer = object()  # type: ignore[assignment]
    live._path = object()  # type: ignore[assignment]
    live._stop_reason = STOP_IDLE
    assert live._resume_after_idle_locked() == LiveError.NoDevice


# frob:tests python/sadi/server/live.py::LiveAcquisition._settings_records
def test_settings_firmware_is_unknown_literal() -> None:
    """The SETTINGS firmware row is the literal 'unknown', never null."""
    _dev, live = _live()
    rows = {(r.scope, r.key): r.value for r in live._settings_records()}
    assert rows[("device", "firmware")] == "unknown"
