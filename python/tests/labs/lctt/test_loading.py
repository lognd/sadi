"""Tests for LCTT tare pooling and load/stress/strain, against hand-computed closed forms."""

# frob:ticket 01M6W7R2XY9DB0PFREY9TZ8D2S

from __future__ import annotations

import math

import numpy as np
import pytest
from typani import Err, Ok

from sadi.labs.lctt.loading import (
    LONG_L0_M,
    SHORT_L0_M,
    LoadingError,
    LoadingInputs,
    LoadingOptions,
    SignPolicy,
    Specimen,
    VoltageUncertainty,
    block_voltage,
    compute_loading,
    default_l0,
    latex_forms,
    pool_tare,
)
from sadi.uncertainty import Measured

G = 9.80665


def _m(v: float, u: float, unit: str) -> Measured:
    res = Measured.create(v, u, unit)
    assert isinstance(res, Ok)
    return res.danger_ok


def _inputs(slope: float = 0.004) -> LoadingInputs:
    return LoadingInputs(
        voltage=_m(1.25, 0.02, "V"),
        tare=_m(0.5, 0.01, "V"),
        slope=_m(slope, 1e-4, "m/V"),
        masses=(_m(0.5, 1e-4, "kg"), _m(1.0, 2e-4, "kg")),
        hanger=_m(0.25, 1e-4, "kg"),
        diameter=_m(0.002, 1e-5, "m"),
        l0=_m(0.08313, 5e-5, "m"),
    )


# frob:tests python/sadi/labs/lctt/loading.py::pool_tare
def test_pool_tare_matches_flat_stats() -> None:
    rng = np.random.default_rng(1)
    blocks = [rng.normal(0.5, 0.01, 50) for _ in range(4)]
    means = [float(b.mean()) for b in blocks]
    sds = [float(b.std(ddof=1)) for b in blocks]
    res = pool_tare(means, sds, [50] * 4)
    assert isinstance(res, Ok)
    flat = np.concatenate(blocks)
    assert res.danger_ok.value == pytest.approx(flat.mean(), rel=1e-12)
    assert res.danger_ok.std_unc == pytest.approx(2 * flat.std(ddof=1), rel=1e-9)


# frob:tests python/sadi/labs/lctt/loading.py::pool_tare
def test_pool_tare_errors() -> None:
    assert pool_tare([], [], []) == Err(LoadingError.NoBlocks)
    assert pool_tare([1.0], [0.1, 0.2], [5]) == Err(LoadingError.LengthMismatch)
    assert pool_tare([1.0], [0.1], [1]) == Err(LoadingError.BadBlock)
    assert pool_tare([math.nan], [0.1], [5]) == Err(LoadingError.BadBlock)


# frob:tests python/sadi/labs/lctt/loading.py::block_voltage
def test_block_voltage_rules() -> None:
    a = block_voltage(1.0, 0.01, 100)
    b = block_voltage(1.0, 0.01, 100, VoltageUncertainty.TWO_S_OVER_SQRT_N)
    assert isinstance(a, Ok) and isinstance(b, Ok)
    assert a.danger_ok.std_unc == pytest.approx(0.02)
    assert b.danger_ok.std_unc == pytest.approx(0.002)
    assert block_voltage(1.0, -1.0, 5) == Err(LoadingError.BadBlock)


# frob:tests python/sadi/labs/lctt/loading.py::default_l0
# frob:tests python/sadi/labs/lctt/loading.py::LoadingOptions.gauge_length
def test_l0_defaults_and_override() -> None:
    assert default_l0(Specimen.SHORT) == SHORT_L0_M == 0.08313
    assert default_l0(Specimen.LONG) == LONG_L0_M == 0.5
    assert LoadingOptions(l0=0.1).gauge_length == 0.1
    assert LoadingOptions(specimen=Specimen.LONG).gauge_length == 0.5


# frob:tests python/sadi/labs/lctt/loading.py::compute_loading
def test_loading_matches_domain_closed_forms() -> None:
    res = compute_loading(_inputs())
    assert isinstance(res, Ok)
    out = res.danger_ok
    f = 1.75 * G
    uf = G * math.sqrt(1e-4**2 + 2e-4**2 + 1e-4**2)
    d, ud = 0.002, 1e-5
    a, ua = math.pi * d**2 / 4, math.pi * d * ud / 2
    sig = f / a
    usig = math.sqrt((uf / a) ** 2 + (f * ua / a**2) ** 2)
    dv, udv = 0.75, math.hypot(0.02, 0.01)
    m, um, l0, ul0 = 0.004, 1e-4, 0.08313, 5e-5
    dl = m * dv
    udl = math.sqrt((dv * um) ** 2 + (m * udv) ** 2)
    eps = dl / l0
    ueps = math.sqrt((udl / l0) ** 2 + (dl * ul0 / l0**2) ** 2)
    assert out.load.value == pytest.approx(f, rel=1e-12)
    assert out.load.std_unc == pytest.approx(uf, rel=1e-9)
    assert out.stress.value == pytest.approx(sig, rel=1e-12)
    assert out.stress.std_unc == pytest.approx(usig, rel=1e-9)
    assert out.strain.value == pytest.approx(eps, rel=1e-12)
    assert out.strain.std_unc == pytest.approx(ueps, rel=1e-9)
    assert out.warnings == ()


# frob:tests python/sadi/labs/lctt/loading.py::compute_loading
def test_default_l0_used_when_absent() -> None:
    base = _inputs()
    no_l0 = base.model_copy(update={"l0": None})
    res = compute_loading(no_l0, LoadingOptions(specimen=Specimen.LONG))
    assert isinstance(res, Ok)
    assert res.danger_ok.strain.value == pytest.approx(0.004 * 0.75 / 0.5, rel=1e-12)


# frob:tests python/sadi/labs/lctt/loading.py::resolve_slope
def test_negative_slope_warns_or_flips() -> None:
    warn = compute_loading(_inputs(-0.004))
    assert isinstance(warn, Ok)
    assert warn.danger_ok.strain.value < 0 and len(warn.danger_ok.warnings) == 1
    flip = compute_loading(_inputs(-0.004), LoadingOptions(sign_policy=SignPolicy.FLIP))
    assert isinstance(flip, Ok)
    assert flip.danger_ok.strain.value == pytest.approx(-warn.danger_ok.strain.value)


# frob:tests python/sadi/labs/lctt/loading.py::compute_loading
def test_bad_diameter_rejected() -> None:
    bad = _inputs().model_copy(update={"diameter": _m(0.0, 0.0, "m")})
    assert compute_loading(bad) == Err(LoadingError.BadLength)


# frob:tests python/sadi/labs/lctt/loading.py::latex_forms
def test_latex_available() -> None:
    res = latex_forms()
    assert isinstance(res, Ok)
    assert set(res.danger_ok) == {"load", "stress", "strain"}
    assert all(res.danger_ok.values())
