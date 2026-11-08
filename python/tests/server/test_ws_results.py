"""Tests wiring ResultsStream to the JobManager sink and the WebSocket router."""

# frob:ticket 01M6WVQWZ9WRFF3D09P2JB9SDC
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from sadi.core.pipeline import Bus
from sadi.jobs.state import JobKey, ResultEnvelope, ResultState
from sadi.server import framing
from sadi.server.app import AppSettings, create_app
from sadi.server.results_stream import ResultsStream

K = JobKey("E")


def _env(dv: int, state: ResultState) -> ResultEnvelope:
    return ResultEnvelope(
        key=K, data_version=dv, result_version=1, state=state, progress=0.5,
        value={"v": 1.0}, emitted_ns=5,
    )  # fmt: skip


def _app(rs: ResultsStream, root: Path) -> TestClient:
    cfg = AppSettings(data_root=root, bus=Bus(), results=rs, require_root_lock=False)
    return TestClient(create_app(cfg))


def _recv_env(ws: object) -> framing.Frame:
    msg = ws.receive_bytes()  # type: ignore[attr-defined]
    res = framing.decode(msg)
    assert res.is_ok
    return res.danger_ok


# frob:tests python/sadi/server/results_stream.py::ResultsStream.job_sink
def test_job_sink_offers_refinements_and_ignores_others() -> None:
    rs = ResultsStream(time_ns=lambda: 1)
    sink = rs.job_sink()
    sink(_env(0, ResultState.STALE))
    assert rs.snapshot() == []
    sink(_env(0, ResultState.REFINING))
    assert [e.state for e in rs.snapshot()] == [ResultState.REFINING]
    rs.push_analytic(3, {})
    sink(_env(1, ResultState.FINAL))  # stale data version: dropped
    assert [e.state for e in rs.snapshot()] == [ResultState.STALE]


# frob:tests python/sadi/server/ws.py::make_ws_router
# frob:tests python/sadi/server/ws.py::StreamHub.__init__
# frob:tests python/sadi/server/ws.py::encode_result
def test_ws_pushes_snapshot_and_live_envelopes(tmp_path: Path) -> None:
    rs = ResultsStream(time_ns=lambda: 5_000_000_000)
    rs.push_analytic(1, {K: {"v": 2.0}})
    with _app(rs, tmp_path) as client, client.websocket_connect("/api/stream") as ws:
        ws.receive_text()  # hello
        snap = _recv_env(ws)
        assert snap.type is framing.FrameType.RESULTS_ENVELOPE
        assert b'"state":"analytic"' in snap.body
        rs.job_sink()(_env(1, ResultState.REFINING))
        live = _recv_env(ws)
        assert b'"state":"refining"' in live.body
        assert live.seq > snap.seq
        rs.push_analytic(2, {})
        stale = _recv_env(ws)
        assert stale.stale


# frob:tests python/sadi/server/ws.py::StreamHub.detach
def test_disconnect_removes_results_client(tmp_path: Path) -> None:
    rs = ResultsStream()
    with _app(rs, tmp_path) as client:
        with client.websocket_connect("/api/stream") as ws:
            ws.receive_text()
        for _ in range(100):
            if not rs._clients:  # noqa: SLF001
                break
            import time

            time.sleep(0.02)
        assert rs._clients == []  # noqa: SLF001
