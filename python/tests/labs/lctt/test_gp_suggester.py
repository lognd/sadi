"""Tests for the GP/c-optimal load selector (seeded synthetic data, no hardware)."""

# frob:ticket 01M71KCTETKE1AE0GZ35MQ11EV

from __future__ import annotations

import math

import numpy as np
import pytest
from typani import Err, Ok

from sadi.core.results import ResultSet
from sadi.labs.lctt.gp_suggester import (
    GpLoadSuggester,
    GpState,
    Kernel,
    Observation,
    cold_start_load,
)
from sadi.labs.lctt.guidance import (
    GuidanceConfig,
    GuidanceInput,
    GuidedRun,
    LoadRange,
    Phase,
    guide,
)

RANGE = LoadRange(min_kg=0.5, max_kg=4.0)
SLOPE = 0.002
SIGMA = 2e-4
TARGET_HW = 8e-5
Z95 = 1.96


def _response(kg: float, rng: np.random.Generator) -> float:
    return 1e-5 + SLOPE * kg + float(rng.normal(0.0, SIGMA))


def _half_width(loads: list[float]) -> float:
    """True 95 % slope half-width for the design (known sigma)."""
    x = np.array(loads)
    sxx = float(((x - x.mean()) ** 2).sum())
    return Z95 * SIGMA / math.sqrt(sxx) if sxx > 0 else math.inf


def _points_to_target(loads_of, seed: int) -> int:
    rng = np.random.default_rng(seed)
    loads: list[float] = []
    sug = GpLoadSuggester(noise_var=SIGMA**2)
    for n in range(1, 40):
        if loads_of == "gp":
            got = sug.suggest(Phase.ELASTIC, ResultSet(n_points=len(loads)), RANGE)
            assert isinstance(got, Ok)
            kg = got.danger_ok.load_kg
        elif loads_of == "even":
            kg = RANGE.min_kg + (RANGE.max_kg - RANGE.min_kg) * n / 12
        else:
            kg = float(rng.uniform(RANGE.min_kg, RANGE.max_kg))
        loads.append(kg)
        sug.observe(kg, _response(kg, rng))
        if _half_width(loads) <= TARGET_HW:
            return n
    return 40


# frob:tests python/sadi/labs/lctt/gp_suggester.py::GpLoadSuggester.suggest
def test_gp_beats_even_and_random_on_points_to_target() -> None:
    gp = [_points_to_target("gp", s) for s in range(5)]
    even = [_points_to_target("even", s) for s in range(5)]
    rand = [_points_to_target("rand", s) for s in range(5)]
    assert sum(gp) < sum(even)
    assert sum(gp) < sum(rand)


# frob:tests python/sadi/labs/lctt/gp_suggester.py::GpLoadSuggester.suggest
@pytest.mark.parametrize("phase", [Phase.ELASTIC, Phase.PLASTIC])
@pytest.mark.parametrize("kernel", [Kernel.MATERN52, Kernel.RBF])
def test_suggestions_stay_in_range_and_are_deterministic(phase: Phase, kernel: Kernel) -> None:
    rng = np.random.default_rng(3)
    obs = tuple(
        Observation(load_kg=k, response=_response(k, rng)) for k in (0.5, 4.0, 2.0, 1.0, 3.0, 2.5)
    )
    outs = []
    for _ in range(2):
        s = GpLoadSuggester(obs, kernel=kernel)
        got = s.suggest(phase, ResultSet(n_points=6), RANGE)
        assert isinstance(got, Ok)
        sug = got.danger_ok
        assert RANGE.contains(sug.load_kg)
        assert len(sug.alternatives) == 3
        assert all(RANGE.contains(a) for a in sug.alternatives)
        assert sug.alternatives[0] == sug.load_kg
        assert sug.expected_gain is not None and sug.expected_gain >= 0.0
        assert sug.gp_state in {st.value for st in GpState}
        outs.append(sug)
    assert outs[0] == outs[1]


# frob:tests python/sadi/labs/lctt/gp_suggester.py::cold_start_load
def test_cold_start_extremes_then_bisection() -> None:
    assert cold_start_load(0, RANGE) == RANGE.min_kg
    assert cold_start_load(1, RANGE) == RANGE.max_kg
    assert cold_start_load(2, RANGE) == pytest.approx(2.25)
    s = GpLoadSuggester()
    got = s.suggest(Phase.ELASTIC, ResultSet(n_points=0), RANGE)
    assert isinstance(got, Ok) and got.danger_ok.load_kg == RANGE.min_kg
    s.observe(0.5, 0.0)
    got = s.suggest(Phase.ELASTIC, ResultSet(n_points=1), RANGE)
    assert isinstance(got, Ok) and got.danger_ok.load_kg == RANGE.max_kg


# frob:tests python/sadi/labs/lctt/gp_suggester.py::GpLoadSuggester.observe
def test_observe_rejects_non_finite() -> None:
    s = GpLoadSuggester()
    assert isinstance(s.observe(float("nan"), 1.0), Err)
    assert isinstance(s.observe(1.0, 2.0), Ok)


# frob:tests python/sadi/labs/lctt/gp_suggester.py::GpLoadSuggester.suggest
def test_bad_data_falls_back_to_even_schedule() -> None:
    obs = tuple(Observation(load_kg=k, response=float("nan")) for k in (0.5, 1.0, 2.0, 3.0))
    got = GpLoadSuggester(obs).suggest(Phase.ELASTIC, ResultSet(n_points=4), RANGE)
    assert isinstance(got, Ok)
    assert RANGE.contains(got.danger_ok.load_kg)
    assert got.danger_ok.gp_state == GpState.UNRELIABLE.value


# frob:tests python/sadi/labs/lctt/guidance.py::guide
def test_guide_defaults_to_gp_and_fills_optional_fields() -> None:
    cfg = GuidanceConfig(load_range=RANGE)
    out = guide(Phase.ELASTIC, GuidanceInput(results=ResultSet()), cfg)
    assert isinstance(out, Ok)
    st = out.danger_ok
    assert st.suggested_load_kg == RANGE.min_kg
    assert st.gp_state == GpState.COLLECTING.value
    assert st.alternatives == ()


# frob:tests python/sadi/labs/lctt/gp_suggester.py::GpLoadSuggester.__init__
# frob:tests python/sadi/labs/lctt/gp_suggester.py::GpLoadSuggester.reset
def test_reset_returns_to_cold_start() -> None:
    obs = tuple(Observation(load_kg=k, response=SLOPE * k) for k in (0.5, 4.0, 2.0, 1.0))
    s = GpLoadSuggester(obs)
    got = s.suggest(Phase.ELASTIC, ResultSet(n_points=4), RANGE)
    assert isinstance(got, Ok) and got.danger_ok.expected_gain is not None
    s.reset()
    assert s.last is None
    got = s.suggest(Phase.ELASTIC, ResultSet(n_points=0), RANGE)
    assert isinstance(got, Ok) and got.danger_ok.load_kg == RANGE.min_kg


# frob:tests python/sadi/labs/lctt/guidance.py::GuidedRun.suggester
def test_guided_run_defaults_to_gp_suggester() -> None:
    assert isinstance(GuidedRun().suggester, GpLoadSuggester)


# frob:ticket 01M72D37RN0VN65DDCSPWHJMJ7
@pytest.mark.parametrize("phase", [Phase.ELASTIC, Phase.PLASTIC])
def test_guidance_never_says_total(phase: Phase) -> None:
    """Cold-start, model-driven and even-schedule guidance all use the masses-only wording."""
    from sadi.labs.lctt.guidance import EvenScheduleSuggester, mass_guidance_text

    texts = []
    sug = GpLoadSuggester(noise_var=SIGMA**2)
    for k in (0, 1):
        got = sug.suggest(phase, ResultSet(n_points=k), RANGE)
        assert isinstance(got, Ok)
        texts.append(got.danger_ok.text)
    for i in range(6):
        sug.observe(0.5 + 0.5 * i, SLOPE * (0.5 + 0.5 * i) + 1e-5 * i * i)
    got = sug.suggest(phase, ResultSet(n_points=6), RANGE)
    assert isinstance(got, Ok)
    texts.append(got.danger_ok.text)
    even = EvenScheduleSuggester().suggest(phase, ResultSet(n_points=2), RANGE)
    assert isinstance(even, Ok)
    texts.append(even.danger_ok.text)
    for t in texts:
        assert "total" not in t.lower()
        assert "hanger is added for you" in t
    assert (
        mass_guidance_text(1.25)
        == "Add 1.250 kg of masses to the hanger (the hanger is added for you)"
    )
