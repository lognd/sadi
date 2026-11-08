"""Tests for the versioned results stream."""

# frob:ticket 01M6W7RAK3KCB1G87VKETJKV0D
from __future__ import annotations

from typani import Err, Ok

from sadi.jobs.state import JobKey, ResultEnvelope, ResultState
from sadi.server.results_stream import (
    PROTOCOL_VERSION,
    ResultsStream,
    StreamErrorCode,
)

K = JobKey("E")


def _stream() -> ResultsStream:
    return ResultsStream(time_ns=lambda: 7)


def _ref(dv: int, state: ResultState = ResultState.REFINING, p: float = 0.5) -> ResultEnvelope:
    return ResultEnvelope(
        key=K, data_version=dv, result_version=1, state=state, progress=p,
        value={"v": 2.0}, emitted_ns=0,
    )  # fmt: skip


# frob:tests python/sadi/server/results_stream.py::ResultsStream
# frob:tests python/sadi/server/results_stream.py::ResultsStream.__init__
# frob:tests python/sadi/server/results_stream.py::ResultsStream.data_version
# frob:tests python/sadi/server/results_stream.py::Connection
# frob:tests python/sadi/server/results_stream.py::Connection.__init__
def test_data_version_tracks_latest_push() -> None:
    s = _stream()
    assert s.data_version == 0
    s.push_analytic(3, {K: {"v": 1.0}})
    s.push_analytic(2, {K: {"v": 9.0}})
    assert s.data_version == 3
    assert s.snapshot()[0].value == {"v": 1.0}


# frob:tests python/sadi/server/results_stream.py::ResultsStream.push_analytic
def test_every_message_carries_versions_and_marker() -> None:
    s, got = _stream(), []
    s.connect(got.append)
    s.push_analytic(1, {K: {"v": 1.0}})
    e = got[0]
    assert (e.protocol_version, e.data_version, e.result_version) == (PROTOCOL_VERSION, 1, 1)
    assert e.state is ResultState.ANALYTIC
    assert e.progress == 0.0


# frob:tests python/sadi/server/results_stream.py::ResultsStream.offer_refinement
def test_refinement_streams_until_final() -> None:
    s, got = _stream(), []
    s.connect(got.append)
    s.push_analytic(1, {K: {"v": 1.0}})
    assert isinstance(s.offer_refinement(_ref(1)), Ok)
    assert isinstance(s.offer_refinement(_ref(1, ResultState.FINAL, 1.0)), Ok)
    assert [e.state for e in got] == [ResultState.ANALYTIC, ResultState.REFINING, ResultState.FINAL]
    assert [e.result_version for e in got] == [1, 2, 3]


# frob:tests python/sadi/server/results_stream.py::ResultsStream.offer_refinement
def test_stale_refinement_discarded_after_new_point() -> None:
    s, got = _stream(), []
    s.connect(got.append)
    s.push_analytic(1, {K: {"v": 1.0}})
    s.push_analytic(2, {K: {"v": 1.5}})
    r = s.offer_refinement(_ref(1))
    assert isinstance(r, Err)
    assert r.danger_err.code is StreamErrorCode.STALE_DATA
    assert got[-1].data_version == 2


# frob:tests python/sadi/server/results_stream.py::ResultsStream.offer_refinement
def test_non_refinement_state_rejected() -> None:
    r = _stream().offer_refinement(_ref(0, ResultState.ANALYTIC))
    assert isinstance(r, Err)
    assert r.danger_err.code is StreamErrorCode.BAD_STATE


# frob:tests python/sadi/server/results_stream.py::ResultsStream.push_analytic
def test_missing_key_marked_stale() -> None:
    s, got = _stream(), []
    s.connect(got.append)
    s.push_analytic(1, {K: {"v": 1.0}})
    s.push_analytic(2, {})
    assert got[-1].state is ResultState.STALE
    assert got[-1].value == {"v": 1.0}
    assert got[-1].data_version == 1


# frob:tests python/sadi/server/results_stream.py::ResultsStream.connect
# frob:tests python/sadi/server/results_stream.py::ResultsStream.snapshot
def test_reconnect_gets_latest_snapshot_only() -> None:
    s = _stream()
    s.push_analytic(1, {K: {"v": 1.0}})
    s.offer_refinement(_ref(1))
    got: list[ResultEnvelope] = []
    s.connect(got.append)
    assert len(got) == 1
    assert got[0].state is ResultState.REFINING
    assert got[0].result_version == 2


# frob:tests python/sadi/server/results_stream.py::ResultsStream.disconnect
def test_disconnect_stops_pushes_and_failing_client_dropped() -> None:
    s, got = _stream(), []
    c = s.connect(got.append)

    def boom(_: ResultEnvelope) -> None:
        raise RuntimeError("x")

    s.connect(boom)
    s.disconnect(c)
    s.disconnect(c)
    s.push_analytic(1, {K: {"v": 1.0}})
    assert got == []
    s.push_analytic(2, {K: {"v": 1.0}})
