"""Smoke tests for the sadi_py binding against the built-in simulator."""

import threading

import numpy as np
import pytest

import sadi_py as sp


def _streaming() -> sp.Session:
    s = sp.open_sim("clean", 1)
    s.connect()
    s.start(sp.AdcMode.DLL_COMPATIBLE)
    return s


# frob:tests crates/sadi-py/python/sadi_py/__init__.pyi::Session.phase
# frob:tests crates/sadi-py/python/sadi_py/__init__.pyi::Session.connect
# frob:tests crates/sadi-py/python/sadi_py/__init__.pyi::Session.query
# frob:tests crates/sadi-py/python/sadi_py/__init__.pyi::Session.start
# frob:tests crates/sadi-py/python/sadi_py/__init__.pyi::Session.read_block
# frob:tests crates/sadi-py/python/sadi_py/__init__.pyi::Session.stop
# frob:tests crates/sadi-py/python/sadi_py/__init__.pyi::Session.close
# frob:tests crates/sadi-py/python/sadi_py/__init__.pyi::Block.__len__
# frob:tests crates/sadi-py/python/sadi_py/__init__.pyi::SessionConfig.__init__
# frob:tests crates/sadi-py/python/sadi_py/__init__.pyi::open_sim
# frob:tests crates/sadi-py/src/session.rs::Session.read_block
# frob:tests crates/sadi-py/src/convert.rs::BlockData.into_py
# frob:tests crates/sadi-py/src/errors.rs::register
def test_lifecycle_and_block_shapes() -> None:
    s = sp.open_sim("clean", 1)
    assert s.phase == sp.Phase.DISCONNECTED
    s.connect()
    assert s.phase == sp.Phase.CONNECTED
    assert s.query().state_byte >= 0
    s.start(sp.AdcMode.DLL_COMPATIBLE)
    assert s.phase == sp.Phase.STREAMING
    b = s.read_block()
    assert b.n_samples > 0
    assert len(b) == b.n_samples
    assert b.volts.shape == (b.n_samples, 4)
    assert b.volts.dtype == np.float64
    assert b.encoder.shape == (b.n_samples,)
    assert isinstance(b.raw, bytes) and len(b.raw) > 0
    tail = s.stop()
    assert isinstance(tail.raw, bytes)
    assert s.phase == sp.Phase.STOPPED
    s.close()
    assert s.phase == sp.Phase.CLOSED


# frob:tests crates/sadi-proto/src/session.rs::RawTap.on_rx
# frob:tests crates/sadi-py/src/session.rs::Session.stop
def test_raw_bytes_cover_the_wire() -> None:
    s = _streaming()
    total = sum(len(s.read_block().raw) for _ in range(3))
    total += len(s.stop().raw)
    assert total >= 3 * 612
    s.close()


# frob:tests crates/sadi-py/src/session.rs::Session.close
def test_consumed_handle_raises() -> None:
    s = sp.open_sim("clean", 1)
    s.close()
    with pytest.raises(sp.ConsumedError) as ei:
        s.connect()
    assert ei.value.kind == "consumed"
    assert isinstance(ei.value, sp.SadiError)
    assert ei.value.detail


# frob:tests crates/sadi-py/src/session.rs::Session.connect
def test_wrong_phase_raises_and_keeps_state() -> None:
    s = sp.open_sim("clean", 1)
    with pytest.raises(sp.PhaseError) as ei:
        s.read_block()
    assert ei.value.kind == "phase"
    assert s.phase == sp.Phase.DISCONNECTED


# frob:tests crates/sadi-py/src/device.rs::open_sim
def test_bad_scenario_kind() -> None:
    with pytest.raises(sp.ScenarioFailure) as ei:
        sp.open_sim("no-such-scenario")
    assert ei.value.kind == "scenario"


# frob:tests crates/sadi-proto/src/session.rs::SessionConfig.read_timeout
# frob:tests crates/sadi-proto/src/session.rs::SessionConfig.idempotence
# frob:tests crates/sadi-proto/src/session.rs::CommandPolicy.max_attempts
# frob:tests crates/sadi-py/src/device.rs::SessionConfig.new
def test_config_must_pair_command_timings() -> None:
    with pytest.raises(sp.ConfigurationError):
        sp.SessionConfig(command_interval_ms=10)


def test_seed_is_reproducible() -> None:
    def grab() -> np.ndarray:
        s = _streaming()
        v = s.read_block().volts.copy()
        s.stop()
        s.close()
        return v

    assert np.array_equal(grab(), grab())


# frob:tests crates/sadi-py/src/codec.rs::encode_command
# frob:tests crates/sadi-py/src/codec.rs::decode_packet
# frob:tests crates/sadi-py/src/codec.rs::adc_to_volts
# frob:tests crates/sadi-py/python/sadi_py/__init__.pyi::encode_command
# frob:tests crates/sadi-py/python/sadi_py/__init__.pyi::decode_packet
# frob:tests crates/sadi-py/python/sadi_py/__init__.pyi::adc_to_volts
def test_codec_helpers() -> None:
    frame = sp.encode_command(sp.CommandKind.QUERY)
    assert isinstance(frame, bytes) and len(frame) > 0
    with pytest.raises(sp.CodecFailure):
        sp.decode_packet(b"\x00" * 10)
    assert isinstance(sp.adc_to_volts(0, sp.AdcRange.PM5_12, sp.AdcMode.IDEAL), float)


# frob:tests crates/sadi-py/src/device.rs::ports
# frob:tests crates/sadi-py/python/sadi_py/__init__.pyi::ports
def test_ports_returns_list() -> None:
    assert isinstance(sp.ports(), list)


# frob:tests crates/sadi-py/python/sadi_py/__init__.pyi::Session.__enter__
# frob:tests crates/sadi-py/python/sadi_py/__init__.pyi::Session.__exit__
def test_context_manager_closes() -> None:
    with sp.open_sim("clean", 1) as s:
        s.connect()
        s.start(sp.AdcMode.IDEAL)
        s.read_block()
    assert s.phase == sp.Phase.CLOSED


# frob:tests crates/sadi-py/src/session.rs::Session.run
def test_gil_released_during_blocking_read() -> None:
    s = _streaming()
    ticks = 0
    stop = threading.Event()

    def spin() -> None:
        nonlocal ticks
        while not stop.is_set():
            ticks += 1

    t = threading.Thread(target=spin)
    t.start()
    for _ in range(5):
        s.read_block()
    stop.set()
    t.join()
    assert ticks > 0
    s.stop()
    s.close()


# frob:tests crates/sadi-py/python/sadi_py/__init__.pyi::Session.restart
# frob:tests crates/sadi-py/python/sadi_py/__init__.pyi::Session.disconnect
# frob:tests crates/sadi-py/src/session.rs::Session.restart
# frob:tests crates/sadi-py/src/session.rs::Session.disconnect
def test_restart_and_disconnect() -> None:
    s = _streaming()
    s.read_block()
    s.stop()
    s.restart()
    assert s.phase == sp.Phase.CONNECTED
    s.disconnect()
    assert s.phase == sp.Phase.DISCONNECTED
    s.close()


# frob:tests crates/sadi-py/python/sadi_py/__init__.pyi::open_serial
# frob:tests crates/sadi-py/src/device.rs::open_serial
def test_open_serial_missing_port_raises() -> None:
    with pytest.raises(sp.SadiError) as ei:
        sp.open_serial("/dev/sadi-no-such-port")
    assert ei.value.detail


# frob:tests crates/sadi-py/src/codec.rs::decode_data_packet
# frob:tests crates/sadi-py/python/sadi_py/__init__.pyi::decode_data_packet
def test_decode_data_packet_rejects_garbage() -> None:
    with pytest.raises(sp.CodecFailure):
        sp.decode_data_packet(b"\x00" * 10, sp.AdcMode.IDEAL)


# frob:tests crates/sadi-py/python/sadi_py/__init__.pyi::Session.reset
# frob:tests crates/sadi-py/python/sadi_py/__init__.pyi::Session.description
# frob:tests crates/sadi-py/python/sadi_py/__init__.pyi::VersionInfo.fw_version
def test_reset_and_description() -> None:
    s = sp.open_sim("clean", 1)
    assert s.description
    s.connect()
    v = s.reset()
    assert isinstance(v.fw_version, float)
    s.close()
