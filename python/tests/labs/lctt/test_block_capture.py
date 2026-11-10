"""Raw-sample block capture: stats, minimum n, ring behaviour, combined uncertainty."""

# frob:ticket 01M72XJMDHV60KRBV1ANWKHKC9
# creates:python/tests/labs/lctt/test_block_capture.py

from __future__ import annotations

import math

from sadi.labs.lctt.capture import (
    BLOCK_SAMPLES_DEFAULT,
    BlockError,
    RawBlockBuffer,
    block_stats,
)


# frob:tests python/sadi/labs/lctt/capture.py::block_stats
def test_block_stats_mean_sd_n() -> None:
    """Mean, sample sd and n are computed over the whole block."""
    st = block_stats([1.0, 2.0, 3.0, 4.0], min_n=2).unwrap()
    assert st.n == 4
    assert st.mean == 2.5
    assert math.isclose(st.sd, math.sqrt(5 / 3))


def test_block_stats_refuses_below_min_n() -> None:
    """A block smaller than the minimum n is refused."""
    res = block_stats([1.0] * 5, min_n=10)
    assert res.is_err
    assert res.danger_err is BlockError.TooFew


# frob:tests python/sadi/labs/lctt/capture.py::RawBlockBuffer.extend
# frob:tests python/sadi/labs/lctt/capture.py::RawBlockBuffer.stats
# frob:tests python/sadi/labs/lctt/capture.py::RawBlockBuffer.clear
# frob:tests python/sadi/labs/lctt/capture.py::RawBlockBuffer.__init__
def test_buffer_keeps_newest_default_block() -> None:
    """The ring holds only the newest BLOCK_SAMPLES_DEFAULT raw samples."""
    buf = RawBlockBuffer()
    buf.extend([0.0] * 100)
    buf.extend([1.0] * BLOCK_SAMPLES_DEFAULT)
    st = buf.stats().unwrap()
    assert st.n == BLOCK_SAMPLES_DEFAULT
    assert st.mean == 1.0
    buf.clear()
    assert buf.stats().is_err


def test_u_mean_combines_sd_over_sqrt_n_with_accuracy() -> None:
    """Uncertainty is sd/sqrt(n) in quadrature with the instrument accuracy."""
    st = block_stats([0.0, 2.0] * 50, min_n=2).unwrap()
    assert math.isclose(st.u_mean(), st.sd / 10)
    assert math.isclose(st.u_mean(0.5), math.hypot(st.sd / 10, 0.5))


def _svc(tmp_path):  # type: ignore[no-untyped-def]
    """Service with a session open past setup."""
    from sadi.core.registry import LabRegistry
    from sadi.labs.lctt.plugin import register
    from sadi.server.schemas import SessionCreate
    from sadi.server.service import SessionService

    labs = LabRegistry()
    assert labs.register(register()).is_ok
    svc = SessionService(tmp_path, labs)
    assert svc.create(SessionCreate(lab="lctt", slug="blk")).is_ok
    assert svc.skip("setup").is_ok
    return svc


def _cal(inputs):  # type: ignore[no-untyped-def]
    """A calibration capture body."""
    from sadi.server.schemas import CaptureBody

    return CaptureBody.model_validate(
        {"phase": "calibration", "inputs": inputs, "window": {"first_raw_seq": 1, "last_raw_seq": 5}}
    )


# frob:tests python/sadi/server/service.py::SessionService._apply_block
def test_service_calibration_uses_server_block_and_refuses_small(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Calibration volts come from the server block; a too-small block is a 422."""
    svc = _svc(tmp_path)
    buf = RawBlockBuffer()
    svc.set_block_source(buf.stats)
    try:
        refused = svc.capture(_cal({"volts": 9.0, "height": 0.01}))
        assert refused.is_err, refused
        buf.extend([2.0, 4.0] * 500)
        got = svc.capture(_cal({"volts": 9.0, "height": 0.01}))
        assert got.is_ok, got
        cur = svc._open  # noqa: SLF001
        pts = svc._replay(cur).danger_ok.view().points  # noqa: SLF001
        inp = pts[0].inputs
        assert inp["volts"] == 3.0
    finally:
        svc.close()


# frob:tests python/sadi/server/live.py::LiveAcquisition.block_stats
def test_live_block_stats_reads_raw_buffer() -> None:
    """LiveAcquisition exposes stats of its raw buffer and refuses while it is small."""
    from sadi.core.pipeline import Bus
    from sadi.server.live import LiveAcquisition

    live = LiveAcquisition(object(), Bus(), watch_poll_s=3600.0, min_block_n=10)  # type: ignore[arg-type]
    assert live.block_stats().is_err
    live._block.extend([1.0] * 20)  # noqa: SLF001
    assert live.block_stats().unwrap().n == 20
