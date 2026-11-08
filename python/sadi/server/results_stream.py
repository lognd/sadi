"""Versioned results stream: instant analytic, progressive refinement, stale markers.

`ResultsStream` is the transport-agnostic core behind the results push. Every message is a
`ResultEnvelope` (protocol_version, key, data_version, result_version, state, progress,
value), so a number never reaches the UI without its version and freshness marker.
After each captured point `push_analytic` publishes the analytic value at once and marks
older refinements stale; `offer_refinement` accepts MC/GP envelopes from the job manager and
discards any whose data_version is already superseded. A (re)connecting client gets the
latest snapshot via `connect`. Documented in docs/server/results-stream.md.
"""

# frob:ticket 01M6W7RAK3KCB1G87VKETJKV0D
from __future__ import annotations

import time
from collections.abc import Callable
from enum import StrEnum
from typing import Final
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from typani import Err, Ok, Result

from sadi.jobs.state import JobKey, ResultEnvelope, ResultState
from sadi.logging_setup import get_logger

_log = get_logger(__name__)

#: Wire protocol version carried in every envelope (`ResultEnvelope.protocol_version`).
PROTOCOL_VERSION: Final = 1

Subscriber = Callable[[ResultEnvelope], None]


class StreamErrorCode(StrEnum):
    """Why a refinement was not published."""

    STALE_DATA = "stale_data"
    BAD_STATE = "bad_state"


class StreamError(BaseModel):
    """Typed rejection of a refinement offer."""

    model_config = ConfigDict(frozen=True)

    code: StreamErrorCode
    key: str
    detail: str = Field(default="")


class Connection:
    """Handle for one connected client; pass it to `ResultsStream.disconnect`."""

    def __init__(self, callback: Subscriber) -> None:
        """Wrap the client's push callback."""
        self.callback = callback


class ResultsStream:
    """Per-key latest-wins publisher of versioned results with snapshot-on-connect."""

    def __init__(self, *, time_ns: Callable[[], int] = time.time_ns) -> None:
        """Start empty at data_version 0; `time_ns` is injectable for tests."""
        self._time_ns = time_ns
        self._data_version = 0
        self._latest: dict[JobKey, ResultEnvelope] = {}
        self._rv: dict[JobKey, int] = {}
        self._clients: list[Connection] = []

    @property
    def data_version(self) -> int:
        """Highest data_version seen from `push_analytic`."""
        return self._data_version

    def snapshot(self) -> list[ResultEnvelope]:
        """Latest envelope per key, ordered by key."""
        return [self._latest[k] for k in sorted(self._latest)]

    def connect(self, callback: Subscriber) -> Connection:
        """Register a client; it is sent the latest snapshot first, then live pushes."""
        conn = Connection(callback)
        self._clients.append(conn)
        snap = self.snapshot()
        _log.info("client connected; replaying %d snapshot envelopes", len(snap))
        for env in snap:
            self._deliver(conn, env)
        return conn

    def disconnect(self, conn: Connection) -> None:
        """Remove a client; unknown connections are ignored."""
        if conn in self._clients:
            self._clients.remove(conn)
            _log.info("client disconnected; %d remain", len(self._clients))
        else:
            _log.debug("disconnect of unknown connection ignored")

    def push_analytic(self, data_version: int, values: dict[JobKey, dict[str, object]]) -> None:
        """Publish analytic values for a new captured point and stale every older result.

        Keys with an older refinement that are absent from `values` are marked stale so no
        number is shown as current for data that has since changed.
        """
        if data_version < self._data_version:
            _log.warning(
                "analytic for old dv=%d ignored (current %d)", data_version, self._data_version
            )
            return
        self._data_version = data_version
        for key in sorted(set(self._latest) - set(values)):
            self._mark_stale(key)
        for key in sorted(values):
            self._publish(key, data_version, ResultState.ANALYTIC, 0.0, values[key])

    def offer_refinement(self, env: ResultEnvelope) -> Result[ResultEnvelope, StreamError]:
        """Publish a refining/final envelope from a job, or reject it as stale or malformed."""
        if env.state not in (ResultState.REFINING, ResultState.FINAL):
            _log.warning("key %s: refinement offer with state %s rejected", env.key, env.state)
            return Err[ResultEnvelope, StreamError](
                StreamError(code=StreamErrorCode.BAD_STATE, key=env.key, detail=str(env.state))
            )
        if env.data_version < self._data_version:
            _log.debug("key %s: refinement dv=%d discarded", env.key, env.data_version)
            return Err[ResultEnvelope, StreamError](
                StreamError(
                    code=StreamErrorCode.STALE_DATA,
                    key=env.key,
                    detail=f"dv {env.data_version} < {self._data_version}",
                )
            )
        out = self._publish(
            env.key, env.data_version, env.state, env.progress, env.value, env.job_id
        )
        return Ok[ResultEnvelope, StreamError](out)

    def _mark_stale(self, key: JobKey) -> None:
        last = self._latest[key]
        if last.state is ResultState.STALE:
            return
        self._publish(
            key, last.data_version, ResultState.STALE, last.progress, last.value, last.job_id
        )

    def _publish(
        self,
        key: JobKey,
        data_version: int,
        state: ResultState,
        progress: float,
        value: dict[str, object] | None,
        job_id: UUID | None = None,
    ) -> ResultEnvelope:
        rv = self._rv.get(key, 0) + 1
        self._rv[key] = rv
        env = ResultEnvelope(
            key=key,
            data_version=data_version,
            result_version=rv,
            state=state,
            progress=progress,
            job_id=job_id,
            value=value,
            emitted_ns=self._time_ns(),
        )
        self._latest[key] = env
        _log.debug("key %s: published dv=%d rv=%d %s", key, data_version, rv, state)
        for conn in list(self._clients):
            self._deliver(conn, env)
        return env

    def _deliver(self, conn: Connection, env: ResultEnvelope) -> None:
        try:
            conn.callback(env)
        except Exception:  # noqa: BLE001 - one bad client must not break the stream
            _log.exception("client callback failed; dropping connection")
            if conn in self._clients:
                self._clients.remove(conn)
