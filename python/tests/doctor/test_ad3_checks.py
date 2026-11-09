"""AD3 doctor checks: sysfs, PowerShell and library discovery faked for linux, wsl and windows."""

# frob:ticket 01M6Z1E0F6PK6K2F6B9VC7QQWM
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from doctor_fakes import FakeProbes, ad3_setup, healthy
from typani import Ok

import sadi.doctor as doctor
from sadi.doctor.checks import ad3
from sadi.doctor.registry import get_remedy
from sadi.doctor.schema import (
    CheckResult,
    CommandRun,
    DoctorReport,
    Os,
    RunOptions,
    SkipReason,
    Status,
)


def _res(out: str = "", code: int = 0) -> Ok[CommandRun, Any]:
    return Ok(CommandRun(argv=("x",), exit_code=code, stdout_tail=out))


def _machine(os: Os, **kw: Any) -> FakeProbes:
    p = healthy()
    p.os = os
    ad3_setup(p, **kw)
    return p


def _run(p: FakeProbes, **opts: object) -> DoctorReport:
    options = RunOptions.model_validate(
        {"render_os": p.os, "data_root": "/home/u/.local/share/sadi", **opts}
    )
    return doctor.run(options, p).unwrap()


def _res_of(report: DoctorReport, cid: str) -> CheckResult:
    return next(r for r in report.results if r.id == cid)


# frob:tests python/sadi/doctor/checks/ad3.py::ad3_010
def test_no_device_skips_everywhere() -> None:
    """No AD3 anywhere skips every AD3 check with NO_DEVICE."""
    for os in (Os.LINUX, Os.WSL, Os.WINDOWS):
        rep = _run(_machine(os))
        for cid in ("AD3-010", "AD3-020", "AD3-030"):
            r = _res_of(rep, cid)
            assert r.status is Status.SKIP and r.skip_reason is SkipReason.NO_DEVICE


# frob:tests python/sadi/doctor/checks/ad3.py::ad3_010
# frob:tests python/sadi/doctor/checks/ad3.py::side_of
# frob:tests python/sadi/doctor/checks/ad3.py::locate
# frob:tests python/sadi/doctor/checks/ad3.py::usbipd_busid
def test_wsl_attached_names_side() -> None:
    """Attached to WSL: ok, headline names wsl, busid found."""
    p = _machine(Os.WSL, sysfs=True)
    r = _res_of(_run(p), "AD3-010")
    assert r.status is Status.PASS and "[wsl]" in r.headline
    assert ad3.usbipd_busid(_ctx(p)) == "2-3"


def _ctx(p: FakeProbes):  # noqa: ANN202
    from sadi.doctor.registry import Ctx

    return Ctx(probes=p, options=RunOptions(render_os=p.os), os=p.os, data_root="/x", facts={})


# frob:tests python/sadi/doctor/checks/ad3.py::ad3_010
def test_wsl_windows_holds_it_warns() -> None:
    """Held by Windows: WARN on-windows-side with the windows fix."""
    r = _res_of(_run(_machine(Os.WSL, pnp=True)), "AD3-010")
    assert r.status is Status.WARN and r.mode == "on-windows-side"
    assert get_remedy("AD3-010", "on-windows-side") is not None


# frob:tests python/sadi/doctor/checks/ad3.py::ad3_010
def test_wsl_without_powershell_skips() -> None:
    """Interop off: SKIP with a reason, never a FAIL."""
    p = _machine(Os.WSL)
    p.tools.pop("powershell.exe")
    r = _res_of(_run(p), "AD3-010")
    assert r.status is Status.SKIP and r.skip_reason is SkipReason.TOOL_MISSING


# frob:tests python/sadi/doctor/checks/ad3.py::ad3_010
def test_windows_native_pnp() -> None:
    """Native Windows reads PnP and names the windows side."""
    r = _res_of(_run(_machine(Os.WINDOWS, pnp=True)), "AD3-010")
    assert r.status is Status.PASS and "[windows]" in r.headline


# frob:tests python/sadi/doctor/checks/ad3.py::ad3_020
# frob:tests python/sadi/doctor/checks/ad3.py::_lib_present
def test_linux_lib_found_and_missing() -> None:
    """Linux: libdwf present is ok, absent fails no-libdwf."""
    p = _machine(Os.LINUX, sysfs=True)
    assert _res_of(_run(p), "AD3-020").mode == "no-libdwf"
    ad3_setup(p, sysfs=True, lib=True)
    r = _res_of(_run(p), "AD3-020")
    assert r.status is Status.PASS and "[linux]" in r.headline


# frob:tests python/sadi/doctor/checks/ad3.py::ad3_020
# frob:tests python/sadi/doctor/checks/ad3.py::_dll_present
def test_wsl_without_lib_but_dll_recommends_detach() -> None:
    """WSL lacks libdwf, Windows has dwf.dll: headline fix detaches and uses Windows python."""
    p = _machine(Os.WSL, sysfs=True, dll=True)
    r = _res_of(_run(p), "AD3-020")
    assert r.status is Status.FAIL and r.mode == "wsl-use-windows"
    assert r.remediation is not None
    text = json.dumps(r.remediation.model_dump(mode="json"), default=str)
    assert "usbipd.exe detach --busid 2-3" in text and "python.exe" in text


# frob:tests python/sadi/doctor/checks/ad3.py::ad3_020
def test_windows_dll_found_and_missing() -> None:
    """Windows: dwf.dll in System32 ok, otherwise no-dwf-dll."""
    p = _machine(Os.WINDOWS, pnp=True)
    assert _res_of(_run(p), "AD3-020").mode == "no-dwf-dll"
    ad3_setup(p, pnp=True, dll=True)
    r = _res_of(_run(p), "AD3-020")
    assert r.status is Status.PASS and "[windows]" in r.headline


# frob:tests python/sadi/doctor/checks/ad3.py::ad3_030
def test_process_holding_device() -> None:
    """WaveForms running warns on every side; none running is ok."""
    for os, kw in (
        (Os.WSL, {"sysfs": True}),
        (Os.WINDOWS, {"pnp": True}),
        (Os.LINUX, {"sysfs": True}),
    ):
        assert _res_of(_run(_machine(os, **kw)), "AD3-030").status is Status.PASS
        r = _res_of(_run(_machine(os, procs="WaveForms\n", **kw)), "AD3-030")
        assert r.status is Status.WARN and r.mode == "held-by-process"
        assert get_remedy("AD3-030", "held-by-process") is not None


# frob:tests python/sadi/doctor/checks/ad3.py::ad3_040
def test_open_is_opt_in_and_reports() -> None:
    """AD3-040 runs only with ad3_open and maps child statuses."""
    p = _machine(Os.WINDOWS, pnp=True, dll=True)
    assert _res_of(_run(p), "AD3-040").status is Status.SKIP
    cases: dict[str, Callable[[CheckResult], bool]] = {
        "ok": lambda r: r.status is Status.PASS,
        "open-failed": lambda r: r.status is Status.FAIL,
        "no-device": lambda r: r.skip_reason is SkipReason.NO_DEVICE,
    }
    for status, pred in cases.items():
        ad3_setup(p, open_json={"status": status, "detail": "busy"})
        r = _res_of(_run(p, ad3_open=True), "AD3-040")
        assert pred(r), (status, r)
        assert "[windows]" in r.headline
    assert get_remedy("AD3-040", "open-failed") is not None


# frob:tests python/sadi/doctor/checks/ad3.py::_deb_workaround_steps
def test_deb_workaround_text_in_remedies() -> None:
    """AD3-020 no-libdwf and AD3-040 open-failed document the extract-deb firmware workaround."""
    p = _machine(Os.LINUX, sysfs=True)
    r = _res_of(_run(p), "AD3-020")
    assert r.remediation is not None
    text = " ".join(st.text for st in r.remediation.steps)
    for needle in (
        "dpkg-deb -x",
        "SADI_DWF_LIB",
        "/usr/share/digilent/waveforms",
        "dialout",
        "No compatible configuration",
    ):
        assert needle in text, needle
    p = _machine(Os.LINUX, sysfs=True, lib=True)
    ad3_setup(p, sysfs=True, lib=True, open_json={"status": "open-failed", "detail": "x"})
    r = _res_of(_run(p, ad3_open=True), "AD3-040")
    assert r.remediation is not None
    assert "dpkg-deb -x" in " ".join(st.text for st in r.remediation.steps)


# frob:tests python/sadi/doctor/checks/ad3.py::ad3_050
def test_override_ok_unset_and_missing() -> None:
    """AD3-050 passes when unset or pointing at a real file, warns otherwise."""
    p = _machine(Os.LINUX, sysfs=True, lib=True)
    assert _res_of(_run(p), "AD3-050").status is Status.PASS
    p.files["/opt/libdwf.so"] = ""
    ad3_setup(p, lib_override="/opt/libdwf.so")
    assert _res_of(_run(p), "AD3-050").status is Status.PASS
    ad3_setup(p, lib_override="/gone/libdwf.so")
    assert _res_of(_run(p), "AD3-050").status is Status.WARN
    assert get_remedy("AD3-050", "override-missing") is not None


# frob:tests python/sadi/doctor/checks/ad3.py::ad3_060
# frob:tests python/sadi/doctor/checks/ad3.py::ad3_070
def test_dialout_and_firmware() -> None:
    """AD3-060/070 pass on a configured Linux box, skip on Windows."""
    p = _machine(Os.LINUX, sysfs=True, lib=True, groups="u dialout\n", firmware=True)
    assert _res_of(_run(p), "AD3-060").status is Status.PASS
    assert _res_of(_run(p), "AD3-070").status is Status.PASS
    q = _machine(Os.LINUX, sysfs=True, lib=True, groups="u adm\n")
    assert _res_of(_run(q), "AD3-060").status is Status.WARN
    assert _res_of(_run(q), "AD3-070").status is Status.FAIL
    n = _machine(Os.LINUX)
    assert _res_of(_run(n), "AD3-060").skip_reason is SkipReason.NO_DEVICE
    assert get_remedy("AD3-060", "no-dialout") is not None
    assert get_remedy("AD3-070", "no-firmware") is not None


# frob:tests python/sadi/doctor/checks/ad3.py::ad3_080
def test_session_is_opt_in_and_maps_statuses() -> None:
    """AD3-080 runs only with ad3_open and maps child statuses."""
    p = _machine(Os.WINDOWS, pnp=True, dll=True)
    assert _res_of(_run(p), "AD3-080").status is Status.SKIP
    for status, want in (("ok", Status.PASS), ("session-failed", Status.FAIL)):
        ad3_setup(p, session_json={"status": status, "detail": "1.2"})
        assert _res_of(_run(p, ad3_open=True), "AD3-080").status is want
    ad3_setup(p, session_json={"status": "no-device", "detail": ""})
    r = _res_of(_run(p, ad3_open=True), "AD3-080")
    assert r.skip_reason is SkipReason.NO_DEVICE
    assert get_remedy("AD3-080", "session-failed") is not None
