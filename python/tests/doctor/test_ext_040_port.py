"""EXT-040: no-udev builds probe an explicit port (--port / SADI_PORT) and report clear steps."""

# frob:ticket 01M6Z5G0SEZ5PNGG11RYBAN6G3
from __future__ import annotations

import json

from doctor_fakes import HEALTHY_DEVICE, FakeProbes
from typani import Ok

from sadi.doctor.checks import ext
from sadi.doctor.devprobe import DeviceFacts
from sadi.doctor.registry import Ctx, get_remedy
from sadi.doctor.schema import CommandRun, Os, RunOptions, Status


def _ctx(*, port: str | None = None, env: str | None = None, device: DeviceFacts | None = None):  # noqa: ANN202
    p = FakeProbes()
    p.commands["-c " + ext.FEATURES_SCRIPT] = Ok(
        CommandRun(argv=("py",), exit_code=0, stdout_tail=json.dumps(["serial"]))
    )
    if env is not None:
        p.environ[ext.PORT_ENV] = env
    if device is not None:
        p.device = device
    return Ctx(probes=p, options=RunOptions(port=port), os=Os.LINUX, data_root="/x", facts={})


# frob:tests python/sadi/doctor/checks/ext.py::ext_040
def test_no_port_warns() -> None:
    """Without any explicit port the old warning stays."""
    out = ext.ext_040(_ctx())
    assert out.status is Status.WARN and out.mode == "no-udev-feature"


# frob:tests python/sadi/doctor/checks/ext.py::ext_040
def test_flag_port_that_answers_passes_as_unsupported() -> None:
    """--port that answers: PASS, enumeration reported as unsupported."""
    out = ext.ext_040(_ctx(port="/dev/ttyUSB0", device=HEALTHY_DEVICE))
    assert out.status is Status.PASS and out.facts["enumeration"] == "unsupported"


# frob:tests python/sadi/doctor/checks/ext.py::explicit_port
def test_env_port_is_used() -> None:
    """SADI_PORT is honoured when --port is absent."""
    ctx = _ctx(env="/dev/ttyUSB1", device=HEALTHY_DEVICE)
    assert ext.explicit_port(ctx) == "/dev/ttyUSB1"
    assert ext.ext_040(ctx).status is Status.PASS


# frob:tests python/sadi/doctor/checks/ext.py::ext_040
def test_dead_port_warns_with_port_fact() -> None:
    """An explicit port that does not open still warns and names the port."""
    out = ext.ext_040(_ctx(port="/dev/ttyUSB9", device=DeviceFacts()))
    assert out.status is Status.WARN and out.facts["port"] == "/dev/ttyUSB9"


# frob:tests python/sadi/doctor/checks/ext.py::_ext_040_udev
def test_remedy_has_port_steps() -> None:
    """The remedy tells the user how to find and pass the port."""
    ctx = _ctx()
    fix = get_remedy("EXT-040", "no-udev-feature")
    assert fix is not None
    text = repr(fix(ctx, ext.ext_040(ctx)))
    assert "SADI_PORT" in text and "ttyUSB" in text
