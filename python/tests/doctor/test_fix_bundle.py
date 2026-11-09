"""Tests for `sadi doctor fix` (dry-run, confirmation, no data) and `--bundle` (no-replace, redaction)."""

# frob:ticket 01M6WA9WYE9D71BBA7AV3H5CGF
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from doctor_fakes import FakeProbes, healthy
from typani import Ok

import sadi.doctor as doctor
import sadi.doctor.fix as fixmod
from sadi.doctor import cli
from sadi.doctor.bundle import capture_log, redact, write_bundle
from sadi.doctor.probes import Probes
from sadi.doctor.schema import (
    Command,
    DoctorError,
    Mutates,
    Os,
    RunOptions,
    Shell,
    Status,
    Step,
    StepKind,
)
from sadi.logging_setup import get_logger


def _broken() -> FakeProbes:
    """A machine whose data root is missing, so DATA-010 fails with a remediation."""
    p = healthy()
    p.dirs.pop(p.data_dir)
    return p


def _with_fixable(monkeypatch: pytest.MonkeyPatch, mutates: Mutates, line: str) -> list[str]:
    """Patch `fix.run` so the failing result carries one fixable command; return the exec log."""
    real = doctor.run

    def fake(options: RunOptions, probes: Probes | None = None):  # noqa: ANN202
        rep = real(options, probes)
        got = rep.unwrap()
        res = got.results[0]
        if res.remediation is None:
            return rep
        cmd = Command(shell=Shell.SH, line=line, fixable=True)
        step = Step.model_construct(
            kind=StepKind.ACTION, text="Do it.", commands=(cmd,), expect="ok", mutates=mutates
        )
        rem = res.remediation.model_copy(update={"steps": (step, *res.remediation.steps[-1:])})
        return Ok(
            got.model_copy(update={"results": (res.model_copy(update={"remediation": rem}),)})
        )

    monkeypatch.setattr(fixmod, "run", fake)
    return []


# frob:tests python/sadi/doctor/fix.py::fix
def test_fix_dry_run_changes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without --apply the command is listed as fixable but never executed."""
    _with_fixable(monkeypatch, Mutates.SYSTEM, "true")
    ran: list[str] = []
    out: list[str] = []
    got = fixmod.fix(
        "DATA-010", RunOptions(), _broken(), out.append, execute=lambda s: ran.append(s) or 0
    )
    assert got.unwrap() == 1
    assert ran == []
    assert "Dry run" in "".join(out)


# frob:tests python/sadi/doctor/fix.py::fix
def test_fix_declined_exits_3(monkeypatch: pytest.MonkeyPatch) -> None:
    """Answering no runs nothing and exits 3."""
    _with_fixable(monkeypatch, Mutates.SYSTEM, "true")
    ran: list[str] = []
    got = fixmod.fix(
        "DATA-010",
        RunOptions(),
        _broken(),
        lambda s: None,
        apply=True,
        ask=lambda q: False,
        execute=lambda s: ran.append(s) or 0,
        is_tty=True,
    )
    assert got.unwrap() == 3
    assert ran == []


# frob:tests python/sadi/doctor/fix.py::fix
def test_fix_confirmed_runs_command(monkeypatch: pytest.MonkeyPatch) -> None:
    """A confirmed fixable system command runs exactly once, then the check is re-run."""
    _with_fixable(monkeypatch, Mutates.SYSTEM, "true")
    ran: list[str] = []
    got = fixmod.fix(
        "DATA-010",
        RunOptions(),
        _broken(),
        lambda s: None,
        apply=True,
        ask=lambda q: True,
        execute=lambda s: ran.append(s) or 0,
        is_tty=True,
    )
    assert ran == ["true"]
    assert got.unwrap() == 1  # data root still missing: the fake fix changed nothing


# frob:tests python/sadi/doctor/fix.py::fix
def test_fix_yes_needs_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    """--yes without a tty and without --non-interactive is refused and runs nothing."""
    _with_fixable(monkeypatch, Mutates.SYSTEM, "true")
    ran: list[str] = []
    got = fixmod.fix(
        "DATA-010",
        RunOptions(),
        _broken(),
        lambda s: None,
        apply=True,
        yes=True,
        execute=lambda s: ran.append(s) or 0,
        is_tty=False,
    )
    assert got.err is DoctorError.FixNeedsTerminal
    assert ran == []


# frob:tests python/sadi/doctor/fix.py::plan
@pytest.mark.parametrize("mutates", [Mutates.DATA, Mutates.NONE])
def test_plan_excludes_non_runnable_classes(
    monkeypatch: pytest.MonkeyPatch, mutates: Mutates
) -> None:
    """data and read-only steps are never planned for execution."""
    _with_fixable(monkeypatch, mutates, "true")
    res = fixmod.run(RunOptions(checks=("DATA-010",)), _broken()).unwrap().results[0]
    assert fixmod.plan(res, "/root") == []


# frob:tests python/sadi/doctor/fix.py::plan
@pytest.mark.parametrize("mutates", [Mutates.DATA_DIR, Mutates.INSTALL])
def test_plan_includes_create_only_classes(
    monkeypatch: pytest.MonkeyPatch, mutates: Mutates
) -> None:
    """data-dir (mkdir of the root) and install (UI build) steps are planned."""
    p = _broken()
    line = f"mkdir -p {p.data_dir}" if mutates is Mutates.DATA_DIR else "true"
    _with_fixable(monkeypatch, mutates, line)
    res = fixmod.run(RunOptions(checks=("DATA-010",)), p).unwrap().results[0]
    assert len(fixmod.plan(res, p.data_dir)) == 1


# frob:tests python/sadi/doctor/fix.py::plan
def test_plan_excludes_commands_touching_data_root(monkeypatch: pytest.MonkeyPatch) -> None:
    """A fixable command that mentions the data root is dropped."""
    p = _broken()
    _with_fixable(monkeypatch, Mutates.SYSTEM, f"touch {p.data_dir}/x")
    res = fixmod.run(RunOptions(checks=("DATA-010",)), p).unwrap().results[0]
    assert fixmod.plan(res, p.data_dir) == []
    assert len(fixmod.plan(res, "/elsewhere")) == 1


# frob:tests python/sadi/doctor/fix.py::fix
def test_fix_unknown_check_and_pass() -> None:
    """Unknown id is an Err; a passing check prints its status and exits 0."""
    assert (
        fixmod.fix("NOPE-1", RunOptions(), healthy(), lambda s: None).err
        is DoctorError.UnknownCheck
    )
    assert fixmod.fix("DATA-010", RunOptions(), healthy(), lambda s: None).unwrap() == 0


# frob:tests python/sadi/doctor/cli.py::main
def test_cli_fix_requires_target(capsys: pytest.CaptureFixture[str]) -> None:
    """`fix` without a check id is a usage error."""
    assert cli.main(["fix"]) == 64
    assert "usage" in capsys.readouterr().err


def _report(p: FakeProbes):  # noqa: ANN202
    """Run DATA-010 against fake probes."""
    return doctor.run(RunOptions(checks=("DATA-010",)), p).unwrap()


# frob:tests python/sadi/doctor/bundle.py::write_bundle
def test_bundle_written_and_redacted(tmp_path: Path) -> None:
    """The zip holds report, log tail and meta; secret-looking lines never appear."""
    report = _report(healthy())
    with capture_log() as cap:
        get_logger("sadi.x").warning("API_KEY=hunter2 leaked")
    dest = tmp_path / "out.zip"
    assert write_bundle(report, cap.lines, dest, Path("/nonexistent-root")).is_ok
    with zipfile.ZipFile(dest) as z:
        assert sorted(z.namelist()) == ["log_tail.txt", "meta.json", "report.json"]
        blob = b"".join(z.read(n) for n in z.namelist()).decode()
    assert "hunter2" not in blob
    assert "[redacted line]" in blob
    assert not list(tmp_path.glob("*.tmp-*"))


# frob:tests python/sadi/doctor/bundle.py::write_bundle
def test_bundle_never_overwrites(tmp_path: Path) -> None:
    """An existing path is refused and left byte-identical."""
    dest = tmp_path / "out.zip"
    dest.write_bytes(b"precious")
    got = write_bundle(_report(healthy()), [], dest, tmp_path / "root")
    assert got.err is DoctorError.BundleExists
    assert dest.read_bytes() == b"precious"


# frob:tests python/sadi/doctor/bundle.py::write_bundle
def test_bundle_refused_inside_data_root(tmp_path: Path) -> None:
    """A path under the data root is refused and nothing is created."""
    root = tmp_path / "root"
    root.mkdir()
    got = write_bundle(_report(healthy()), [], root / "b.zip", root)
    assert got.err is DoctorError.BundleInsideDataRoot
    assert list(root.iterdir()) == []


# frob:tests python/sadi/doctor/bundle.py::redact
def test_redact_masks_home_and_secrets() -> None:
    """Secret lines are masked and the home directory becomes ~."""
    out = redact("ok /home/u/x\npassword: abc", home="/home/u")
    assert out == "ok ~/x\n[redacted line]"


# frob:tests python/sadi/doctor/cli.py::main
def test_cli_bundle_flag(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """--bundle writes the zip next to a normal run and a second run refuses the same path."""
    dest = tmp_path / "b.zip"
    args = [
        "--json",
        "--check",
        "CLK-010",
        "--data-root",
        str(tmp_path / "root"),
        "--bundle",
        str(dest),
    ]
    assert cli.main(args) in (0, 1, 2)
    assert dest.exists()
    assert cli.main(args) == 64
    assert "never overwrites" in capsys.readouterr().err


def test_status_enum_used() -> None:
    """Guard that Status import stays meaningful for fix output."""
    assert Status.PASS.value == "pass" and Os.LINUX
