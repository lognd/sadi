"""Progressive MC and GP job tasks: tightening intervals, supersede, seeded determinism."""

# frob:ticket 01M6W7R3G88NFY3N76MPX6X3ZQ
from __future__ import annotations

import threading
from collections.abc import Generator
from uuid import UUID

import pytest
from typani import Err, Ok

from sadi.jobs import JobState, ResultState
from sadi.jobs.pool import CancelToken
from sadi.jobs.tasks._drive import Steps, TaskError
from sadi.jobs.tasks.gp import gp_steps, run_gp
from sadi.jobs.tasks.mc import mc_steps, run_mc
from sadi.jobs.testing import Interleaver, JobHarness, Step, make_spec
from sadi.uncertainty.montecarlo import McSampler

MC_INPUTS: dict[str, object] = {
    "fn": "numpy:multiply",
    "means": [3.0, 2.0],
    "cov": [[0.04, 0.0], [0.0, 0.01]],
    "seed": 7,
    "target": 2000,
    "batch_size": 100,
}


def as_script(steps_fn):  # noqa: ANN001, ANN201
    """Adapt a task core to a harness script (Tick -> Step; Err -> raise)."""

    def script(inputs: dict[str, object]) -> Generator[Step, bool, dict[str, object]]:
        gen: Steps = steps_fn(inputs)
        try:
            tick = next(gen)
            while True:
                cancelled = yield Step(fraction=tick.fraction, partial=tick.partial)
                tick = gen.send(cancelled)
        except StopIteration as stop:
            res = stop.value
        if isinstance(res, Err):
            raise RuntimeError(str(res.danger_err))
        return res.danger_ok

    return script


def make_token() -> tuple[CancelToken, list[dict[str, object]], threading.Event]:
    """A real CancelToken wired to a list sink (no throttling)."""
    sent: list[dict[str, object]] = []
    flag = threading.Event()
    return CancelToken(UUID(int=1), flag, sent.append, 0), sent, flag


def collect(steps: Steps) -> tuple[list[dict[str, object]], object]:
    """Drive a core to the end with no cancel, returning partials and the final Result."""
    partials: list[dict[str, object]] = []
    try:
        tick = next(steps)
        while True:
            partials.append(tick.partial or {})
            tick = steps.send(False)
    except StopIteration as stop:
        return partials, stop.value
    return partials, None


# frob:tests python/sadi/jobs/tasks/mc.py::mc_steps
def test_mc_interval_tightens_and_matches_single_shot() -> None:
    partials, res = collect(mc_steps(MC_INPUTS))
    assert isinstance(res, Ok)
    widths = [float(p["halfwidth_mean"]) for p in partials]  # type: ignore[arg-type]
    assert len(partials) == 20
    assert widths[-1] < widths[0]
    assert [p["n"] for p in partials] == list(range(100, 2001, 100))
    sampler = McSampler.create(
        __import__("numpy").multiply,
        [3.0, 2.0],
        [[0.04, 0.0], [0.0, 0.01]],
        seed=7,
        batch_size=100,
    ).danger_ok
    shot = sampler.run_to(2000).danger_ok.model_dump()
    final = res.danger_ok
    assert {k: final[k] for k in shot} == shot


# frob:tests python/sadi/jobs/tasks/mc.py::mc_steps
def test_mc_chunking_does_not_change_result() -> None:
    _, a = collect(mc_steps(MC_INPUTS))
    _, b = collect(mc_steps({**MC_INPUTS, "batches_per_tick": 7}))
    assert a.danger_ok == b.danger_ok  # type: ignore[union-attr]


# frob:tests python/sadi/jobs/tasks/mc.py::mc_steps
@pytest.mark.parametrize(
    "bad",
    [
        {"fn": "nonsense"},
        {"fn": "no_such_module_xyz:f"},
        {"target": 1},
        {"cov": [[1.0]]},
    ],
)
def test_mc_bad_inputs_are_typed_errors(bad: dict[str, object]) -> None:
    _, res = collect(mc_steps({**MC_INPUTS, **bad}))
    assert isinstance(res, Err)
    assert res.danger_err in (TaskError.BadInputs, TaskError.BadFunction)


# frob:tests python/sadi/jobs/tasks/mc.py::run_mc
def test_run_mc_emits_progress_and_cancel_discards() -> None:
    token, sent, flag = make_token()
    out = run_mc(MC_INPUTS, token)
    assert out["n"] == 2000
    assert len(sent) == 20
    assert sent[-1]["fraction"] == 1.0
    token2, sent2, flag2 = make_token()
    flag2.set()
    assert run_mc(MC_INPUTS, token2) == {}
    assert len(sent2) == 1


# frob:tests python/sadi/jobs/tasks/mc.py::run_mc
def test_run_mc_error_raises_at_worker_boundary() -> None:
    token, _, _ = make_token()
    with pytest.raises(RuntimeError, match="mc job"):
        run_mc({**MC_INPUTS, "fn": "nonsense"}, token)


# frob:tests python/sadi/jobs/tasks/mc.py::mc_steps
def test_new_data_version_supersedes_inflight_mc() -> None:
    h = JobHarness(workers=1)
    try:
        h.register("mc", as_script(mc_steps))
        h.start()
        assert isinstance(h.manager.submit(make_spec(1, key="mc", task="mc", **MC_INPUTS)), Ok)
        for _ in range(4):  # started + 3 progress points
            h.step(0)
        newer = {**MC_INPUTS, "seed": 8}
        assert isinstance(
            h.manager.submit(make_spec(2, key="mc", task="mc", data_version=2, **newer)), Ok
        )
        h.settle()
        h.run_slot(0)
        h.run_slot(0)
        h.settle()
        states = {o.job_id: o.state for o in h.outcomes}
        assert states[UUID(int=1)] is JobState.SUPERSEDED
        assert states[UUID(int=2)] is JobState.DONE
        final = [e for e in h.envelopes if e.state is ResultState.FINAL]
        assert len(final) == 1 and final[0].data_version == 2
        assert final[0].value is not None and final[0].value["seed"] == 8
        refining_dv = {e.data_version for e in h.envelopes if e.state is ResultState.REFINING}
        assert 1 in refining_dv
    finally:
        h.close()


# frob:tests python/sadi/jobs/tasks/mc.py::mc_steps
@pytest.mark.parametrize("seed", range(10))
def test_mc_supersede_interleavings_are_deterministic(seed: int) -> None:
    def run() -> tuple[list[str], dict[str, object] | None]:
        h = JobHarness(workers=2)
        try:
            h.register("mc", as_script(mc_steps))
            h.start()
            h.manager.submit(make_spec(1, key="mc", task="mc", **MC_INPUTS))
            h.manager.submit(
                make_spec(2, key="mc", task="mc", data_version=2, **{**MC_INPUTS, "seed": 9})
            )
            il = Interleaver(h, seed)
            assert isinstance(il.run_until_idle(), Ok)
            final = [e for e in h.envelopes if e.state is ResultState.FINAL]
            assert len(final) == 1 and final[0].data_version == 2
            return list(il.trace), final[0].value
        finally:
            h.close()

    assert run() == run()


GP_INPUTS: dict[str, object] = {
    "x": [[0.0], [0.4], [1.0], [2.0]],
    "y": [0.0, 0.38, 0.84, 0.91],
    "candidates": [[0.2], [0.7], [1.5], [4.0]],
}


# frob:tests python/sadi/jobs/tasks/gp.py::gp_steps
def test_gp_progressive_best_fit_and_suggestion() -> None:
    partials, res = collect(gp_steps(GP_INPUTS))
    assert isinstance(res, Ok)
    lml = [float(p["log_marginal"]) for p in partials]  # type: ignore[arg-type]
    assert lml == sorted(lml)
    assert partials[-1]["lengthscale"] == res.danger_ok["lengthscale"]
    sugg = res.danger_ok["suggestion"]
    assert sugg["index"] == 3  # type: ignore[index]  # farthest from the data is most uncertain


# frob:tests python/sadi/jobs/tasks/gp.py::gp_steps
@pytest.mark.parametrize(
    "bad",
    [{"y": [0.0]}, {"x": [[0.0, 1.0]]}, {"y": [0.0, 0.1, float("nan"), 1.0]}, {"noise": -1.0}],
)
def test_gp_bad_inputs(bad: dict[str, object]) -> None:
    _, res = collect(gp_steps({**GP_INPUTS, **bad}))
    assert isinstance(res, Err) and res.danger_err is TaskError.BadInputs


# frob:tests python/sadi/jobs/tasks/gp.py::gp_steps
def test_gp_no_candidates_means_no_suggestion() -> None:
    _, res = collect(gp_steps({**GP_INPUTS, "candidates": []}))
    assert isinstance(res, Ok) and "suggestion" not in res.danger_ok


# frob:tests python/sadi/jobs/tasks/gp.py::run_gp
def test_run_gp_cancel_and_supersede() -> None:
    token, sent, flag = make_token()
    flag.set()
    assert run_gp(GP_INPUTS, token) == {}
    assert len(sent) == 1
    h = JobHarness(workers=1)
    try:
        h.register("gp", as_script(gp_steps))
        h.start()
        h.manager.submit(make_spec(1, key="gp", task="gp", **GP_INPUTS))
        for _ in range(3):
            h.step(0)
        extra = {
            **GP_INPUTS,
            "x": [[0.0], [0.4], [1.0], [2.0], [3.0]],
            "y": [0, 0.38, 0.84, 0.9, 0.5],
        }
        h.manager.submit(make_spec(2, key="gp", task="gp", data_version=2, **extra))
        h.settle()
        h.run_slot(0)
        h.run_slot(0)
        h.settle()
        states = {o.job_id: o.state for o in h.outcomes}
        assert states[UUID(int=1)] is JobState.SUPERSEDED
        assert states[UUID(int=2)] is JobState.DONE
    finally:
        h.close()
