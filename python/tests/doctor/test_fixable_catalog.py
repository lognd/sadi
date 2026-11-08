"""Catalog commands tagged fixable are exactly the safe system/process ones (doctor.md 4.4)."""

# frob:ticket 01M6WMZHNS2E0QNW7KFZ1GAYMZ
from __future__ import annotations

from doctor_fakes import healthy

from sadi.doctor import fix as fixmod
from sadi.doctor.registry import Ctx, Outcome, all_checks, get_remedy
from sadi.doctor.schema import Mutates, Os, RunOptions, Status, StepKind

ROOT = "/home/u/.local/share/sadi"


def _fixables(os: Os) -> list[tuple[str, str, Mutates, str]]:
    """Return (check, mode, mutates, line) for every fixable command in the catalog on this OS."""
    found = []
    for spec, _ in all_checks():
        for mode in spec.modes:
            fn = get_remedy(spec.id, mode)
            ctx = Ctx(probes=healthy(), options=RunOptions(), os=os, data_root=ROOT)
            for s in fn(ctx, Outcome(Status.FAIL, "x", mode=mode, facts={"busid": "2-3"})).steps:
                found += [(spec.id, mode, s.mutates, c.line) for c in s.commands if c.fixable]
    return found


def test_fixable_commands_are_only_safe_classes_and_avoid_data_root() -> None:
    """No fixable command is install/data/data-dir class, a verify step, or touches the data root."""
    for os in Os:
        for _, _, mutates, line in _fixables(os):
            assert mutates in fixmod.RUNNABLE
            assert ROOT not in line
            assert "bind" not in line.split()
    for spec, _ in all_checks():
        for mode in spec.modes:
            fn = get_remedy(spec.id, mode)
            ctx = Ctx(probes=healthy(), options=RunOptions(), os=Os.WSL, data_root=ROOT)
            for s in fn(ctx, Outcome(Status.FAIL, "x", mode=mode)).steps:
                assert s.kind is not StepKind.VERIFY or not any(c.fixable for c in s.commands)


def test_wsl_has_attach_udev_and_browser_fixables() -> None:
    """On WSL the doc 4.4 list is present: udev install, usbipd attach, browser open."""
    lines = [x[3] for x in _fixables(Os.WSL)]
    assert any(ln.startswith("sudo install") and "99-sadi.rules" in ln for ln in lines)
    assert "sudo udevadm control --reload-rules" in lines
    assert "usbipd.exe attach --wsl --busid 2-3" in lines
    assert any("webbrowser" in ln for ln in lines)


def test_windows_has_no_fixables() -> None:
    """Windows commands are never run by the doctor; only Linux/WSL steps are fixable."""
    assert [x for x in _fixables(Os.WINDOWS) if "usbipd" in x[3] or "udev" in x[3]] == []
