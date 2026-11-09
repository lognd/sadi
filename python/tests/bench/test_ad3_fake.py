"""FakeDwf determinism, protocol conformance, inject helpers and the SADI ADC loopback."""

# frob:ticket 01M6WSQ57BQ8EZYECPGPFQFWB7
from __future__ import annotations

import inspect
import math

import pytest
from pydantic import ValidationError
from typani import Err, Ok

from sadi.bench.ad3 import (
    AcqMode,
    AcqState,
    Channel,
    DwfBackend,
    DwfCode,
    IoNode,
    OutNode,
    WaveFunction,
)
from sadi.bench.ad3.backend import OpenDevice
from sadi.bench.ad3.dll import CtypesBackend
from sadi.bench.ad3.fake import FakeConfig, FakeDwf, ScopeCal, waveform
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


# frob:ticket 01M6XAKF7X3NKXQ7X8GACKX0VE
# frob:tests python/sadi/bench/ad3/fake.py::FakeDwf.version
# frob:tests python/sadi/bench/ad3/fake.py::FakeDwf.set_on_close
# frob:tests python/sadi/bench/ad3/fake.py::FakeDwf.enumerate_devices
# frob:tests python/sadi/bench/ad3/fake.py::FakeDwf.open
# frob:tests python/sadi/bench/ad3/fake.py::FakeDwf.close
# frob:tests python/sadi/bench/ad3/fake.py::FakeDwf.auto_configure
# frob:tests python/sadi/bench/ad3/fake.py::FakeDwf.__init__
def test_session_calls() -> None:
    """Session calls on a typed FakeDwf: version, on-close range, enumerate, open, auto, close."""
    f: FakeDwf = FakeDwf(FakeConfig(serial="SN:TEST"))
    assert f.version().unwrap() == "fake-3.0"
    assert isinstance(f.set_on_close(1), Ok)
    bad = f.set_on_close(3)
    assert isinstance(bad, Err) and bad.unwrap_err().code == DwfCode.CALL_FAILED
    infos = f.enumerate_devices().unwrap()
    assert [i.serial for i in infos] == ["SN:TEST"]
    dev = f.open(0).unwrap()
    assert isinstance(f.auto_configure(dev, True), Ok)
    assert f.close(dev).unwrap().index == 0
    assert isinstance(f.auto_configure(dev, True), Err)


# frob:ticket 01M6XAKF7X3NKXQ7X8GACKX0VE
# frob:tests python/sadi/bench/ad3/fake.py::FakeDwf.out_node_enable
# frob:tests python/sadi/bench/ad3/fake.py::FakeDwf.out_node_function
# frob:tests python/sadi/bench/ad3/fake.py::FakeDwf.out_node_frequency
# frob:tests python/sadi/bench/ad3/fake.py::FakeDwf.out_node_amplitude
# frob:tests python/sadi/bench/ad3/fake.py::FakeDwf.out_node_offset
# frob:tests python/sadi/bench/ad3/fake.py::FakeDwf.out_configure
# frob:tests python/sadi/bench/ad3/fake.py::FakeDwf.in_reset
# frob:tests python/sadi/bench/ad3/fake.py::FakeDwf.in_channel_enable
# frob:tests python/sadi/bench/ad3/fake.py::FakeDwf.in_channel_range
# frob:tests python/sadi/bench/ad3/fake.py::FakeDwf.in_channel_offset
# frob:tests python/sadi/bench/ad3/fake.py::FakeDwf.in_frequency
# frob:tests python/sadi/bench/ad3/fake.py::FakeDwf.in_buffer_size
# frob:tests python/sadi/bench/ad3/fake.py::FakeDwf.in_acquisition_mode
# frob:tests python/sadi/bench/ad3/fake.py::FakeDwf.in_configure
# frob:tests python/sadi/bench/ad3/fake.py::FakeDwf.in_status
# frob:tests python/sadi/bench/ad3/fake.py::FakeDwf.in_data
# frob:tests python/sadi/bench/ad3/fake.py::waveform
def test_analog_out_in_round_trip() -> None:
    """Every analog out/in setter on a typed FakeDwf takes effect in the latched capture."""
    f: FakeDwf = FakeDwf()
    dev = f.open(-1).unwrap()
    ch = Channel(0)
    node = OutNode.CARRIER
    assert isinstance(f.in_reset(dev), Ok)
    for res in (
        f.out_node_enable(dev, ch, node, True),
        f.out_node_function(dev, ch, node, WaveFunction.SQUARE),
        f.out_node_frequency(dev, ch, node, 1000.0),
        f.out_node_amplitude(dev, ch, node, 1.0),
        f.out_node_offset(dev, ch, node, 0.5),
        f.out_configure(dev, ch, True),
        f.in_channel_enable(dev, ch, True),
        f.in_channel_range(dev, ch, 10.0),
        f.in_channel_offset(dev, ch, 0.0),
        f.in_frequency(dev, 4000.0),
        f.in_buffer_size(dev, 4),
        f.in_acquisition_mode(dev, AcqMode.SINGLE),
        f.in_configure(dev, True, True),
    ):
        assert isinstance(res, Ok)
    assert f.in_status(dev, True).unwrap() == AcqState.DONE
    assert f.in_data(dev, ch, 4).unwrap() == [1.5, 1.5, -0.5, -0.5]
    assert f.in_data(dev, ch, 2).unwrap() == [1.5, 1.5]
    assert waveform(WaveFunction.SQUARE, 0.25) == 1.0
    assert waveform(WaveFunction.SQUARE, 0.75) == -1.0
    assert waveform(WaveFunction.NOISE, 0.0) is None
    assert isinstance(f.in_reset(dev), Ok)
    assert f.in_status(dev, False).unwrap() == AcqState.READY
    assert isinstance(f.in_data(dev, ch, 4), Err)


# frob:ticket 01M6XAKF7X3NKXQ7X8GACKX0VE
# frob:tests python/sadi/bench/ad3/fake.py::FakeDwf.io_enable
# frob:tests python/sadi/bench/ad3/fake.py::FakeDwf.io_node_set
# frob:tests python/sadi/bench/ad3/fake.py::FakeDwf.io_configure
# frob:tests python/sadi/bench/ad3/fake.py::FakeDwf.io_status
# frob:tests python/sadi/bench/ad3/fake.py::FakeDwf.io_node_status
# frob:tests python/sadi/bench/ad3/fake.py::FakeDwf.dio_output_enable
# frob:tests python/sadi/bench/ad3/fake.py::FakeDwf.dio_output
# frob:tests python/sadi/bench/ad3/fake.py::FakeDwf.dio_configure
# frob:tests python/sadi/bench/ad3/fake.py::FakeDwf.dio_status
# frob:tests python/sadi/bench/ad3/fake.py::FakeDwf.dio_input
def test_io_calls() -> None:
    """Analog and digital IO calls on a typed FakeDwf store and read back their values."""
    f: FakeDwf = FakeDwf()
    dev = f.open(-1).unwrap()
    assert isinstance(f.io_enable(dev, True), Ok)
    assert isinstance(f.io_node_set(dev, Channel(0), IoNode(0), 1.0), Ok)
    assert isinstance(f.io_configure(dev), Ok)
    assert isinstance(f.io_status(dev), Ok)
    assert f.io_node_status(dev, Channel(0), IoNode(0)).unwrap() == 1.0
    assert f.io_node_status(dev, Channel(1), IoNode(0)).unwrap() == 0.0
    assert isinstance(f.dio_output_enable(dev, 0b0110), Ok)
    assert isinstance(f.dio_output(dev, 0b0101), Ok)
    assert isinstance(f.dio_configure(dev), Ok)
    assert isinstance(f.dio_status(dev), Ok)
    assert f.dio_input(dev).unwrap() == 0b0100
    f.close(dev).unwrap()
    assert isinstance(f.dio_input(dev), Err)
    assert isinstance(f.io_node_status(dev, Channel(0), IoNode(0)), Err)


# frob:ticket 01M6XAKF7X3NKXQ7X8GACKX0VE
# frob:tests python/sadi/bench/ad3/backend.py::DwfBackend.version
# frob:tests python/sadi/bench/ad3/backend.py::DwfBackend.set_on_close
# frob:tests python/sadi/bench/ad3/backend.py::DwfBackend.enumerate_devices
# frob:tests python/sadi/bench/ad3/backend.py::DwfBackend.open
# frob:tests python/sadi/bench/ad3/backend.py::DwfBackend.close
# frob:tests python/sadi/bench/ad3/backend.py::DwfBackend.auto_configure
# frob:tests python/sadi/bench/ad3/backend.py::DwfBackend.out_node_enable
# frob:tests python/sadi/bench/ad3/backend.py::DwfBackend.out_node_function
# frob:tests python/sadi/bench/ad3/backend.py::DwfBackend.out_node_frequency
# frob:tests python/sadi/bench/ad3/backend.py::DwfBackend.out_node_amplitude
# frob:tests python/sadi/bench/ad3/backend.py::DwfBackend.out_node_offset
# frob:tests python/sadi/bench/ad3/backend.py::DwfBackend.out_configure
# frob:tests python/sadi/bench/ad3/backend.py::DwfBackend.in_reset
# frob:tests python/sadi/bench/ad3/backend.py::DwfBackend.in_channel_enable
# frob:tests python/sadi/bench/ad3/backend.py::DwfBackend.in_channel_range
# frob:tests python/sadi/bench/ad3/backend.py::DwfBackend.in_channel_offset
# frob:tests python/sadi/bench/ad3/backend.py::DwfBackend.in_frequency
# frob:tests python/sadi/bench/ad3/backend.py::DwfBackend.in_buffer_size
# frob:tests python/sadi/bench/ad3/backend.py::DwfBackend.in_acquisition_mode
# frob:tests python/sadi/bench/ad3/backend.py::DwfBackend.in_configure
# frob:tests python/sadi/bench/ad3/backend.py::DwfBackend.in_status
# frob:tests python/sadi/bench/ad3/backend.py::DwfBackend.in_data
# frob:tests python/sadi/bench/ad3/backend.py::DwfBackend.io_enable
# frob:tests python/sadi/bench/ad3/backend.py::DwfBackend.io_node_set
# frob:tests python/sadi/bench/ad3/backend.py::DwfBackend.io_configure
# frob:tests python/sadi/bench/ad3/backend.py::DwfBackend.io_status
# frob:tests python/sadi/bench/ad3/backend.py::DwfBackend.io_node_status
# frob:tests python/sadi/bench/ad3/backend.py::DwfBackend.dio_output_enable
# frob:tests python/sadi/bench/ad3/backend.py::DwfBackend.dio_output
# frob:tests python/sadi/bench/ad3/backend.py::DwfBackend.dio_configure
# frob:tests python/sadi/bench/ad3/backend.py::DwfBackend.dio_status
# frob:tests python/sadi/bench/ad3/backend.py::DwfBackend.dio_input
def test_backends_match_protocol_signatures() -> None:
    """FakeDwf and CtypesBackend expose every DwfBackend method with the same parameters."""
    proto_methods = [
        n for n, v in vars(DwfBackend).items() if callable(v) and not n.startswith("_")
    ]
    assert len(proto_methods) == 32
    for impl in (FakeDwf, CtypesBackend):
        for name in proto_methods:
            want = list(inspect.signature(getattr(DwfBackend, name)).parameters)
            got = list(inspect.signature(getattr(impl, name)).parameters)
            assert got == want, f"{impl.__name__}.{name}"


# frob:tests python/sadi/bench/inject.py::PinMap
def test_sadi_pins_match_bench_wiring() -> None:
    """SADI_PINS encodes W1->ACH0 (+), W2->ACH2 (-), supply monitor on scope ch 0."""
    from sadi.bench.inject import SADI_PINS

    assert (SADI_PINS.lvdt.out_channel, SADI_PINS.lvdt.sadi_channel) == (0, 0)
    assert SADI_PINS.lvdt.polarity == "positive"
    assert (SADI_PINS.load.out_channel, SADI_PINS.load.sadi_channel) == (1, 2)
    assert SADI_PINS.load.polarity == "negative"
    assert SADI_PINS.supply_scope_channel == 0


# frob:ticket 01M6Z3FR6FP6TTP9BW4MHJSE85
def _stream_fake(mode: AcqMode) -> tuple[FakeDwf, OpenDevice]:
    """Build an opened fake armed in `mode` with a 1 kHz ramp on ch 0 sampled at 4 kHz."""
    f = FakeDwf()
    dev = f.open(0).unwrap()
    ch, node = Channel(0), OutNode.CARRIER
    f.out_node_enable(dev, ch, node, True)
    f.out_node_function(dev, ch, node, WaveFunction.RAMP_UP)
    f.out_node_frequency(dev, ch, node, 1000.0)
    f.out_node_amplitude(dev, ch, node, 1.0)
    f.out_configure(dev, ch, True)
    f.in_channel_enable(dev, ch, True)
    f.in_channel_range(dev, ch, 10.0)
    f.in_frequency(dev, 2000.0)
    f.in_buffer_size(dev, 3)
    assert isinstance(f.in_acquisition_mode(dev, mode), Ok)
    assert isinstance(f.in_configure(dev, True, True), Ok)
    return f, dev


# frob:tests python/sadi/bench/ad3/fake.py::FakeDwf
@pytest.mark.parametrize("mode", [AcqMode.RECORD, AcqMode.SCAN_SCREEN, AcqMode.SCAN_SHIFT])
def test_streaming_blocks_are_phase_continuous(mode: AcqMode) -> None:
    """Streaming polls stay TRIGGERED and latch contiguous blocks of one waveform."""
    f, dev = _stream_fake(mode)
    ch = Channel(0)
    got: list[float] = []
    for _ in range(3):
        assert f.in_status(dev, True).unwrap() == AcqState.TRIGGERED
        got += f.in_data(dev, ch, 3).unwrap()
    # 2 kHz sampling of a 1 kHz ramp alternates between 2 phases (-1, 0)
    assert got == pytest.approx([-1.0, 0.0] * 4 + [-1.0])
    # polls without read_data do not advance the stream
    assert f.in_status(dev, False).unwrap() == AcqState.TRIGGERED
    # re-arming restarts the stream
    f.in_configure(dev, True, True)
    f.in_status(dev, True)
    assert f.in_data(dev, ch, 1).unwrap() == pytest.approx([-1.0])


# frob:tests python/sadi/bench/ad3/fake.py::FakeDwf
def test_unsupported_mode_rejected() -> None:
    """Oversample stays unsupported and is reported as a value."""
    f = FakeDwf()
    dev = f.open(0).unwrap()
    res = f.in_acquisition_mode(dev, AcqMode.OVERSAMPLE)
    assert isinstance(res, Err)
