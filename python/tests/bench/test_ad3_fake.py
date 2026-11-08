"""FakeDwf determinism, protocol conformance, inject helpers and the SADI ADC loopback."""

# frob:ticket 01M6WSQ57BQ8EZYECPGPFQFWB7
from __future__ import annotations

import math

import pytest
from pydantic import ValidationError
from typani import Err

from sadi.bench.ad3 import Channel, DwfBackend, DwfCode, OutNode, WaveFunction
from sadi.bench.ad3.fake import FakeConfig, FakeDwf, ScopeCal
from sadi.bench.inject import (
    PinMap,
    SignalRoute,
    capture,
    counts_to_volts,
    inject_dc,
    inject_lvdt,
    stop_injection,
    volts_to_counts,
)

PINS = PinMap(
    lvdt=SignalRoute(out_channel=0, scope_channel=0),
    load=SignalRoute(out_channel=1, scope_channel=1),
)


def _open(fake: FakeDwf):
    """Open the fake and return the device handle."""
    return fake.open(-1).unwrap()


# frob:tests python/sadi/bench/ad3/fake.py::FakeDwf
def test_satisfies_protocol() -> None:
    """FakeDwf is assignable to DwfBackend and enumerates one AD3."""
    be: DwfBackend = FakeDwf()
    assert be.enumerate_devices().unwrap()[0].serial.startswith("SN:")


# frob:tests python/sadi/bench/ad3/fake.py::FakeDwf
def test_open_close_typestate() -> None:
    """Closed handles return HANDLE_CLOSED; a second open without close fails."""
    f = FakeDwf()
    dev = _open(f)
    assert isinstance(f.open(0), Err)
    f.close(dev).unwrap()
    res = f.out_configure(dev, Channel(0), True)
    assert isinstance(res, Err) and res.unwrap_err().code == DwfCode.HANDLE_CLOSED
    assert isinstance(f.open(5), Err)


# frob:tests python/sadi/bench/inject.py::capture
def test_sine_sampled_exactly() -> None:
    """A 1 kHz sine sampled at 8 kHz gives the analytic values."""
    f = FakeDwf()
    dev = _open(f)
    inject_lvdt(f, dev, PINS, 2.0, 1000.0, 0.5).unwrap()
    got = capture(f, dev, 0, 8000.0, 8).unwrap()
    for k, v in enumerate(got):
        assert v == pytest.approx(0.5 + 2.0 * math.sin(2 * math.pi * k / 8), abs=1e-12)


# frob:tests python/sadi/bench/ad3/fake.py::FakeDwf
def test_deterministic_noise_and_cal() -> None:
    """Same seed gives identical noisy captures; gain/offset apply; clipping at range."""
    cfg = FakeConfig(seed=7, cal={0: ScopeCal(gain=2.0, offset_v=0.1, noise_v=0.01)})
    runs = []
    for _ in range(2):
        f = FakeDwf(cfg)
        dev = _open(f)
        inject_dc(
            f, dev, PinMap(lvdt=SignalRoute(out_channel=1), load=SignalRoute(out_channel=0)), 1.0
        ).unwrap()
        runs.append(capture(f, dev, 0, 1000.0, 64).unwrap())
    assert runs[0] == runs[1]
    assert sum(runs[0]) / 64 == pytest.approx(2.1, abs=0.02)
    f = FakeDwf(FakeConfig(cal={0: ScopeCal(gain=10.0)}))
    dev = _open(f)
    inject_dc(
        f, dev, PinMap(lvdt=SignalRoute(out_channel=1), load=SignalRoute(out_channel=0)), 2.0
    ).unwrap()
    assert max(capture(f, dev, 0, 1000.0, 4, range_v=4.0).unwrap()) == 2.0


# frob:tests python/sadi/bench/ad3/fake.py::FakeDwf.set_custom
def test_custom_and_ramp_waveforms() -> None:
    """Custom buffers and ramps generate the expected samples."""
    f = FakeDwf()
    dev = _open(f)
    f.set_custom(Channel(0), [0.0, 1.0, 2.0, 3.0])
    f.out_node_enable(dev, Channel(0), OutNode.CARRIER, True)
    f.out_node_frequency(dev, Channel(0), OutNode.CARRIER, 1000.0)
    f.out_configure(dev, Channel(0), True)
    assert capture(f, dev, 0, 4000.0, 4).unwrap() == [0.0, 1.0, 2.0, 3.0]
    f.custom.clear()
    f.out_node_function(dev, Channel(0), OutNode.CARRIER, WaveFunction.RAMP_UP)
    f.out_node_amplitude(dev, Channel(0), OutNode.CARRIER, 1.0)
    assert capture(f, dev, 0, 4000.0, 4).unwrap() == [-1.0, -0.5, 0.0, 0.5]


# frob:tests python/sadi/bench/ad3/fake.py::FakeDwf
def test_rejects_bad_arguments() -> None:
    """Unsupported functions, bad ranges and unlatched reads are Err(CALL_FAILED)."""
    f = FakeDwf()
    dev = _open(f)
    for res in (
        f.out_node_function(dev, Channel(0), OutNode.CARRIER, WaveFunction.NOISE),
        f.out_node_frequency(dev, Channel(0), OutNode.CARRIER, 0.0),
        f.in_buffer_size(dev, 10**9),
        f.in_channel_range(dev, Channel(0), -1.0),
        f.in_channel_enable(dev, Channel(7), True),
        f.in_data(dev, Channel(0), 4),
    ):
        assert isinstance(res, Err) and res.unwrap_err().code == DwfCode.CALL_FAILED


# frob:tests python/sadi/bench/inject.py::PinMap
def test_pinmap_validation() -> None:
    """PinMap rejects shared out channels, negatives and unknown keys."""
    with pytest.raises(ValidationError):
        PinMap(lvdt=SignalRoute(out_channel=0), load=SignalRoute(out_channel=0))
    with pytest.raises(ValidationError):
        SignalRoute(out_channel=-1)
    with pytest.raises(ValidationError):
        PinMap.model_validate({"lvdt": {"out_channel": 0}, "load": {"out_channel": 1}, "x": 1})


# frob:tests python/sadi/bench/inject.py::stop_injection
def test_stop_injection_silences_outputs() -> None:
    """After stop_injection the scope reads zero."""
    f = FakeDwf()
    dev = _open(f)
    inject_dc(f, dev, PINS, 1.5).unwrap()
    stop_injection(f, dev, PINS).unwrap()
    assert capture(f, dev, 1, 1000.0, 2).unwrap() == [0.0, 0.0]


# frob:tests python/sadi/bench/inject.py::volts_to_counts
def test_loopback_fake_to_sadi_adc_model() -> None:
    """FakeDwf waveform -> capture -> ideal SADI 16-bit ADC counts matches the analytic counts."""
    fs = 5.12
    f = FakeDwf()
    dev = _open(f)
    inject_lvdt(f, dev, PINS, 2.0, 1000.0).unwrap()
    volts = capture(f, dev, 0, 16000.0, 32).unwrap()
    counts = [volts_to_counts(v, fs) for v in volts]
    expect = [volts_to_counts(2.0 * math.sin(2 * math.pi * k / 16), fs) for k in range(32)]
    assert all(abs(a - b) <= 1 for a, b in zip(counts, expect, strict=True))
    for c, v in zip(counts, volts, strict=True):
        assert counts_to_volts(c, fs) == pytest.approx(v, abs=fs / 65535)
    assert volts_to_counts(99.0, fs) == 65535 and volts_to_counts(-99.0, fs) == 0
