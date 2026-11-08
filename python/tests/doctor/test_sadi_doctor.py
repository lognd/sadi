"""Doctor tests: per-mode fault injection with remediation text, catalog invariants, read-only lint."""

# frob:ticket 01M6WA9WYE9D71BBA7AV3H5CGF
from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path

import pytest
from doctor_fakes import FakeProbes, healthy
from typani import Err, Ok

import sadi.doctor as doctor
from sadi.doctor import cli
from sadi.doctor.registry import all_checks, get_remedy
from sadi.doctor.render_text import render
from sadi.doctor.schema import (
    CommandRun,
    DoctorReport,
    Layer,
    Mutates,
    Os,
    ProbeError,
    RunOptions,
    Severity,
    SkipReason,
    Status,
    StepKind,
)
from sadi.plugins.doctor import DoctorFinding
from sadi.plugins.doctor import Severity as FSev

ROOT = "/home/u/.local/share/sadi"
SYS = "/sys/bus/usb/devices"
Mut = Callable[[FakeProbes], None]


def _import_fail(stderr: str, code: int = 1) -> Mut:
    def f(p: FakeProbes) -> None:
        p.commands["-c import sadi_py"] = Ok(
            CommandRun(argv=("py",), exit_code=code, stderr_tail=stderr)
        )

    return f


def _set(**kw: object) -> Mut:
    def f(p: FakeProbes) -> None:
        for k, v in kw.items():
            setattr(p, k, v)

    return f


def _priv(p: FakeProbes) -> None:
    p.bind = "denied"


def _drop_root(p: FakeProbes) -> None:
    p.dirs.pop(ROOT)


def _file_root(p: FakeProbes) -> None:
    p.dirs.pop(ROOT)
    p.files[ROOT] = ""


def _ro_root(p: FakeProbes) -> None:
    p.read_only.add(ROOT)


def _no_usb(p: FakeProbes) -> None:
    p.dirs[SYS] = []


def _odd_pid(p: FakeProbes) -> None:
    p.files[f"{SYS}/1-1/idProduct"] = "9999\n"


def _no_driver(p: FakeProbes) -> None:
    p.links.clear()


def _no_node(p: FakeProbes) -> None:
    p.dirs["/dev"] = ["null"]


def _usbipd(state: str) -> Mut:
    def f(p: FakeProbes) -> None:
        p.dirs[SYS] = []
        p.tools["usbipd.exe"] = "/usbipd.exe"
        p.commands["list"] = Ok(
            CommandRun(
                argv=("usbipd.exe",),
                exit_code=0,
                stdout_tail=f"2-3    0403:6010  USB Serial Converter   {state}\n",
            )
        )

    return f


def _no_group(p: FakeProbes) -> None:
    p.node_ok = (False, "dialout")
    p.groups = ["users"]


def _in_group_no_access(p: FakeProbes) -> None:
    p.node_ok = (False, "dialout")


# (check id, mode, os, mutator)
CASES: list[tuple[str, str, Os, Mut]] = [
    ("PLAT-010", "wsl1", Os.WSL, _set(files={"/proc/version": "Linux 4.4.0-Microsoft"})),
    ("PLAT-010", "unsupported-os", Os.WINDOWS, _set(os=Os.WINDOWS)),
    ("PLAT-030", "c-locale", Os.LINUX, _set(enc=("ascii", False))),
    ("PLAT-030", "non-utf8-console", Os.WINDOWS, _set(enc=("cp1252", False))),
    ("PLAT-050", "failpoints-armed", Os.LINUX, _set(environ={"SADI_FAILPOINTS": "x"})),
    ("PY-010", "too-old", Os.LINUX, _set(py=(3, 9, 1))),
    ("PY-020", "not-installed", Os.MACOS, _set(dists={})),
    ("PY-030", "missing", Os.WINDOWS, _set(dists={"sadi": "0.1.0"})),
    ("PY-030", "import-error", Os.LINUX, _set(import_errors={"numpy": "boom"})),
    ("PY-030", "pydantic-v1", Os.LINUX, lambda p: p.dists.update(pydantic="1.10.0")),
    ("PY-040", "uv-missing", Os.LINUX, _set(tools={})),
    (
        "EXT-010",
        "not-installed",
        Os.LINUX,
        _import_fail("ModuleNotFoundError: No module named 'sadi_py'"),
    ),
    (
        "EXT-010",
        "abi-mismatch",
        Os.WINDOWS,
        _import_fail("Traceback\nImportError: DLL load failed"),
    ),
    ("EXT-010", "crashed", Os.MACOS, _import_fail("", 139)),
    (
        "EXT-010",
        "timeout",
        Os.LINUX,
        lambda p: p.commands.update(
            {"-c import sadi_py": Err(ProbeError(kind="timeout", detail="20s"))}
        ),
    ),
    ("WEB-010", "missing-bundle", Os.LINUX, _set(bundle=(False, 0))),
    ("NET-010", "no-loopback", Os.LINUX, _set(loopback=False)),
    ("NET-010", "localhost-not-loopback", Os.WINDOWS, _set(localhost=["10.0.0.5"])),
    ("NET-020", "port-in-use-other", Os.LINUX, _set(bind="in-use")),
    ("NET-020", "port-privileged", Os.LINUX, _priv),
    ("NET-020", "bind-denied", Os.WINDOWS, _set(bind="denied")),
    ("DATA-010", "missing", Os.LINUX, _drop_root),
    ("DATA-010", "not-a-directory", Os.LINUX, _file_root),
    ("DATA-010", "not-writable", Os.MACOS, _ro_root),
    ("DATA-020", "network-fs", Os.LINUX, _set(fs="nfs")),
    ("DATA-020", "drvfs-9p", Os.WSL, _set(fs="9p")),
    ("DATA-020", "fat-exfat", Os.LINUX, _set(fs="vfat")),
    ("DATA-030", "below-minimum", Os.LINUX, _set(free=10**8)),
    ("DATA-030", "low", Os.LINUX, _set(free=5 * 1024**3)),
    ("DATA-090", "spill-present", Os.LINUX, _set(spills=["/x/a.spill"])),
    ("USB-020", "no-device", Os.LINUX, _no_usb),
    ("USB-020", "unknown-ftdi-pid", Os.LINUX, _odd_pid),
    ("USB-020", "device-on-windows-side", Os.WSL, _usbipd("Not shared")),
    ("USB-020", "shared-not-attached", Os.WSL, _usbipd("Shared")),
    ("USB-030", "no-driver", Os.LINUX, _no_driver),
    ("USB-040", "node-missing", Os.LINUX, _no_node),
    ("USB-050", "not-in-group", Os.LINUX, _no_group),
    ("USB-050", "node-not-accessible", Os.LINUX, _in_group_no_access),
    ("CLK-010", "clock-before-build", Os.LINUX, _set(clock=1_000_000.0)),
    ("RES-010", "single-core", Os.LINUX, _set(cpus=1)),
    ("RES-020", "low-memory", Os.LINUX, _set(mem=700 * 1024**2)),
    ("RES-020", "very-low-memory", Os.WINDOWS, _set(mem=100 * 1024**2)),
    ("RES-030", "low-nofile", Os.MACOS, _set(nofile=256)),
    ("BRW-010", "no-browser", Os.LINUX, _set(browser=False)),
    ("BRW-010", "wsl-no-wslview", Os.WSL, _set(browser=False)),
    (
        "PLG-010",
        "plugin-error",
        Os.LINUX,
        _set(
            findings=[
                DoctorFinding(
                    plugin_id="p",
                    severity=FSev.ERROR,
                    code="plugin.import_failed",
                    message="bad",
                    fixes=("1. Reinstall p",),
                )
            ]
        ),
    ),
    (
        "PLG-010",
        "plugin-warning",
        Os.LINUX,
        _set(
            findings=[
                DoctorFinding(
                    plugin_id="p", severity=FSev.WARNING, code="w", message="meh", fixes=()
                )
            ]
        ),
    ),
]


def _run(p: FakeProbes, os: Os, **opts: object) -> DoctorReport:
    options = RunOptions(render_os=os, **opts)  # type: ignore[arg-type]
    return doctor.run(options, p).unwrap()


def test_healthy_machine_is_ready() -> None:
    """A healthy fake machine passes everything and exits 0."""
    report = _run(healthy(), Os.LINUX, data_root=ROOT)
    bad = [r.id for r in report.results if r.status in (Status.FAIL, Status.WARN)]
    assert bad == []
    assert report.summary.verdict == "ready"
    assert doctor.exit_code(report) == 0


# frob:tests python/sadi/doctor/__init__.py::exit_code
# frob:tests python/sadi/doctor/__init__.py::run
# frob:tests python/sadi/doctor/__init__.py::summarize
# frob:tests python/sadi/doctor/checks/brw.py::brw_010
# frob:tests python/sadi/doctor/checks/clk.py::clk_010
# frob:tests python/sadi/doctor/checks/data.py::data_010
# frob:tests python/sadi/doctor/checks/data.py::data_020
# frob:tests python/sadi/doctor/checks/data.py::data_030
# frob:tests python/sadi/doctor/checks/data.py::data_090
# frob:tests python/sadi/doctor/checks/ext.py::ext_010
# frob:tests python/sadi/doctor/checks/net.py::net_010
# frob:tests python/sadi/doctor/checks/net.py::net_020
# frob:tests python/sadi/doctor/checks/plat.py::plat_010
# frob:tests python/sadi/doctor/checks/plat.py::plat_030
# frob:tests python/sadi/doctor/checks/plat.py::plat_050
# frob:tests python/sadi/doctor/checks/plg.py::plg_010
# frob:tests python/sadi/doctor/checks/py.py::py_010
# frob:tests python/sadi/doctor/checks/py.py::py_020
# frob:tests python/sadi/doctor/checks/py.py::py_030
# frob:tests python/sadi/doctor/checks/py.py::py_040
# frob:tests python/sadi/doctor/checks/res.py::res_010
# frob:tests python/sadi/doctor/checks/res.py::res_020
# frob:tests python/sadi/doctor/checks/res.py::res_030
# frob:tests python/sadi/doctor/checks/res.py::worker_count
# frob:tests python/sadi/doctor/checks/usb.py::ftdi_sysfs
# frob:tests python/sadi/doctor/checks/usb.py::usb_020
# frob:tests python/sadi/doctor/checks/usb.py::usb_030
# frob:tests python/sadi/doctor/checks/usb.py::usb_040
# frob:tests python/sadi/doctor/checks/usb.py::usb_050
# frob:tests python/sadi/doctor/checks/usb.py::usbipd_ftdi
# frob:tests python/sadi/doctor/checks/web.py::web_010
# frob:tests python/sadi/doctor/cli.py::main
# frob:tests python/sadi/doctor/registry.py::all_checks
# frob:tests python/sadi/doctor/registry.py::check
# frob:tests python/sadi/doctor/registry.py::fail
# frob:tests python/sadi/doctor/registry.py::ok
# frob:tests python/sadi/doctor/registry.py::remedy
# frob:tests python/sadi/doctor/registry.py::skip
# frob:tests python/sadi/doctor/registry.py::warn
# frob:tests python/sadi/doctor/render_text.py::render
# frob:tests python/sadi/doctor/steps.py::action
# frob:tests python/sadi/doctor/steps.py::cmd
# frob:tests python/sadi/doctor/steps.py::manual
# frob:tests python/sadi/doctor/steps.py::shell_for
# frob:tests python/sadi/doctor/steps.py::verify
@pytest.mark.parametrize(("check_id", "mode", "os", "mutate"), CASES, ids=lambda x: str(x)[:30])
def test_fault_injection_yields_mode_and_remedy(
    check_id: str, mode: str, os: Os, mutate: Mut
) -> None:
    """Breaking one fact produces exactly that mode with a numbered, verified remediation."""
    p = healthy()
    p.os = os
    mutate(p)
    port = 80 if mode == "port-privileged" else 8000
    report = _run(p, os, data_root=ROOT, allow_network_fs=False, api_port=port)
    result = next(r for r in report.results if r.id == check_id)
    assert result.mode == mode, result.headline
    assert result.status in (Status.WARN, Status.FAIL)
    rem = result.remediation
    assert rem is not None and rem.os is os
    assert rem.steps[-1].kind is StepKind.VERIFY
    assert f"--check {check_id}" in rem.steps[-1].commands[0].line
    assert all(s.expect for s in rem.steps)
    text = render(report)
    assert f"{check_id}" in text and "Expect:" in text
    assert text.isascii()


def test_declared_modes_are_all_injected() -> None:
    """Every failure mode the catalog declares has a fault-injection case (no dead modes)."""
    declared = {(s.id, m) for s, _ in all_checks() for m in s.modes}
    covered = {(c, m) for c, m, _, _ in CASES}
    assert declared - covered == set()
    assert covered - declared == set()


def test_every_mode_has_a_remedy_for_every_os() -> None:
    """Remedies build for all four OSes and honour the schema invariants."""
    from sadi.doctor.registry import Ctx, Outcome

    for spec, _ in all_checks():
        for mode in spec.modes:
            fn = get_remedy(spec.id, mode)
            assert fn is not None, f"{spec.id}/{mode}"
            for os in Os:
                ctx = Ctx(probes=healthy(), options=RunOptions(), os=os, data_root=ROOT)
                fix = fn(ctx, Outcome(Status.FAIL, "x", mode=mode))
                assert fix.steps, f"{spec.id}/{mode}/{os}"
                for s in fix.steps:
                    assert s.kind is not StepKind.VERIFY
                    if s.mutates is Mutates.DATA:
                        assert not s.commands


def test_prerequisite_failure_skips_dependants() -> None:
    """A failed dependency skips dependants with a reason rather than running them."""
    p = healthy()
    _no_usb(p)
    report = _run(p, Os.LINUX, data_root=ROOT)
    skipped = {r.id: r for r in report.results if r.status is Status.SKIP}
    assert skipped["USB-030"].skip_reason is SkipReason.PREREQUISITE_FAILED
    assert "USB-050" in skipped


def test_crashing_check_becomes_probe_error() -> None:
    """An exception inside a probe is reported as a probe-error fail, not a doctor crash."""
    p = healthy()

    def boom() -> tuple[bool, int]:
        raise RuntimeError("kaput")

    p.web_bundle = boom  # type: ignore[method-assign]
    report = _run(p, Os.LINUX, data_root=ROOT)
    r = next(r for r in report.results if r.id == "WEB-010")
    assert r.status is Status.FAIL and r.mode == "probe-error"
    assert r.evidence.error is not None and "kaput" in r.evidence.error.detail
    assert r.remediation is not None


def test_selection_and_unknown_ids() -> None:
    """--check/--layer/--skip filter; an unknown id is a DoctorError."""
    p = healthy()
    only = _run(p, Os.LINUX, checks=("PY-010",), data_root=ROOT)
    assert [r.id for r in only.results] == ["PY-010"]
    layer = _run(p, Os.LINUX, layers=(Layer.CLK,), data_root=ROOT)
    assert {r.layer for r in layer.results} == {Layer.CLK}
    skipped = _run(p, Os.LINUX, skip=("PY-010",), data_root=ROOT)
    assert "PY-010" not in {r.id for r in skipped.results}
    assert doctor.run(RunOptions(checks=("ZZZ-999",)), p).is_err


def test_exit_codes_and_verdict() -> None:
    """Blocker fail is 2, other fail is 1, warnings-only is 0."""
    p = healthy()
    p.browser = False
    assert doctor.exit_code(_run(p, Os.LINUX, data_root=ROOT)) == 0
    p = healthy()
    _no_usb(p)
    r = _run(p, Os.LINUX, data_root=ROOT)
    assert doctor.exit_code(r) == 1 and r.summary.verdict == "degraded"
    p = healthy()
    p.py = (3, 9, 0)
    r = _run(p, Os.LINUX, data_root=ROOT)
    assert doctor.exit_code(r) == 2 and r.summary.verdict == "blocked"
    assert r.summary.first_action


def test_json_round_trip() -> None:
    """The report serialises to JSON and validates back unchanged."""
    p = healthy()
    _no_usb(p)
    report = _run(p, Os.LINUX, data_root=ROOT)
    again = DoctorReport.model_validate_json(report.model_dump_json())
    assert again == report
    assert json.loads(report.model_dump_json())["schema_version"] == 1


def test_data_root_resolution() -> None:
    """--data-root beats SADI_DATA_ROOT beats the per-user default."""
    p = healthy()
    assert doctor.resolve_data_root(RunOptions(), p) == p.data_dir
    p.environ["SADI_DATA_ROOT"] = "/env"
    assert doctor.resolve_data_root(RunOptions(), p) == "/env"
    assert doctor.resolve_data_root(RunOptions(data_root="/flag"), p) == "/flag"


def test_cli_list_explain_and_usage(capsys: pytest.CaptureFixture[str]) -> None:
    """The CLI lists checks, explains one, and rejects unknown ids with 64."""
    assert cli.main(["list"]) == 0
    assert "USB-020" in capsys.readouterr().out
    assert cli.main(["explain", "USB-020"]) == 0
    assert "no-device" in capsys.readouterr().out
    assert cli.main(["explain", "NOPE-1"]) == 64
    assert cli.main(["--check", "ZZZ-999"]) == 64
    assert cli.main(["--bogus"]) == 64


def test_cli_json_on_real_machine(capsys: pytest.CaptureFixture[str]) -> None:
    """A real run emits a valid JSON report and an exit code in {0,1,2}."""
    code = cli.main(["--json", "--check", "CLK-010", "--check", "PY-010"])
    out = capsys.readouterr().out
    assert code in (0, 1, 2)
    assert DoctorReport.model_validate_json(out).results


def test_severity_enum_has_blocker() -> None:
    """Guard: exit-code mapping relies on the BLOCKER severity name."""
    assert Severity.BLOCKER.value == "blocker"


def test_doctor_is_read_only() -> None:
    """No doctor source writes files, spawns shells, or mutates the system."""
    banned = re.compile(
        r"\.write_text\(|\.write_bytes\(|os\.remove|os\.unlink|shutil\.|\bmkdir\(|makedirs|"
        r"shell=True|os\.system|\bchmod\(|\.touch\(|open\([^)]*['\"][wax+]"
    )
    src = Path(doctor.__file__).parent
    hits = [
        f"{p.name}:{i}"
        for p in src.rglob("*.py")
        for i, line in enumerate(p.read_text().splitlines(), 1)
        if banned.search(line)
        and "disk_usage" not in line
        and "shutil.which" not in line
        and "import shutil" not in line
        and "chmod 660" not in line
    ]
    assert hits == []


def test_catalog_docs_are_current() -> None:
    """docs/doctor-checks.md matches `sadi-doctor docs` output."""
    doc = Path(__file__).resolve().parents[3] / "docs" / "doctor-checks.md"
    assert (
        doc.read_text() == cli.catalog_markdown() + "\n"
        or doc.read_text() == cli.catalog_markdown()
    )


# frob:tests python/sadi/doctor/probes.py::Probes.bind_state
# frob:tests python/sadi/doctor/probes.py::Probes.browser_available
# frob:tests python/sadi/doctor/probes.py::Probes.cpu_count
# frob:tests python/sadi/doctor/probes.py::Probes.disk_free
# frob:tests python/sadi/doctor/probes.py::Probes.dist_version
# frob:tests python/sadi/doctor/probes.py::Probes.encoding
# frob:tests python/sadi/doctor/probes.py::Probes.env
# frob:tests python/sadi/doctor/probes.py::Probes.exists
# frob:tests python/sadi/doctor/probes.py::Probes.fstype
# frob:tests python/sadi/doctor/probes.py::Probes.import_error
# frob:tests python/sadi/doctor/probes.py::Probes.is_dir
# frob:tests python/sadi/doctor/probes.py::Probes.listdir
# frob:tests python/sadi/doctor/probes.py::Probes.localhost_addrs
# frob:tests python/sadi/doctor/probes.py::Probes.loopback_ok
# frob:tests python/sadi/doctor/probes.py::Probes.machine
# frob:tests python/sadi/doctor/probes.py::Probes.mem_available
# frob:tests python/sadi/doctor/probes.py::Probes.node_access
# frob:tests python/sadi/doctor/probes.py::Probes.nofile_soft
# frob:tests python/sadi/doctor/probes.py::Probes.now
# frob:tests python/sadi/doctor/probes.py::Probes.os_kind
# frob:tests python/sadi/doctor/probes.py::Probes.os_version
# frob:tests python/sadi/doctor/probes.py::Probes.plugin_findings
# frob:tests python/sadi/doctor/probes.py::Probes.py_version
# frob:tests python/sadi/doctor/probes.py::Probes.python_exe
# frob:tests python/sadi/doctor/probes.py::Probes.read_text
# frob:tests python/sadi/doctor/probes.py::Probes.readlink
# frob:tests python/sadi/doctor/probes.py::Probes.requires_python
# frob:tests python/sadi/doctor/probes.py::Probes.run
# frob:tests python/sadi/doctor/probes.py::Probes.spill_files
# frob:tests python/sadi/doctor/probes.py::Probes.user_data_dir
# frob:tests python/sadi/doctor/probes.py::Probes.user_groups
# frob:tests python/sadi/doctor/probes.py::Probes.web_bundle
# frob:tests python/sadi/doctor/probes.py::Probes.which
# frob:tests python/sadi/doctor/probes.py::Probes.writable
# frob:tests python/sadi/doctor/probes.py::RealProbes.bind_state
# frob:tests python/sadi/doctor/probes.py::RealProbes.browser_available
# frob:tests python/sadi/doctor/probes.py::RealProbes.cpu_count
# frob:tests python/sadi/doctor/probes.py::RealProbes.disk_free
# frob:tests python/sadi/doctor/probes.py::RealProbes.dist_version
# frob:tests python/sadi/doctor/probes.py::RealProbes.encoding
# frob:tests python/sadi/doctor/probes.py::RealProbes.env
# frob:tests python/sadi/doctor/probes.py::RealProbes.exists
# frob:tests python/sadi/doctor/probes.py::RealProbes.fstype
# frob:tests python/sadi/doctor/probes.py::RealProbes.import_error
# frob:tests python/sadi/doctor/probes.py::RealProbes.is_dir
# frob:tests python/sadi/doctor/probes.py::RealProbes.listdir
# frob:tests python/sadi/doctor/probes.py::RealProbes.localhost_addrs
# frob:tests python/sadi/doctor/probes.py::RealProbes.loopback_ok
# frob:tests python/sadi/doctor/probes.py::RealProbes.machine
# frob:tests python/sadi/doctor/probes.py::RealProbes.mem_available
# frob:tests python/sadi/doctor/probes.py::RealProbes.node_access
# frob:tests python/sadi/doctor/probes.py::RealProbes.nofile_soft
# frob:tests python/sadi/doctor/probes.py::RealProbes.now
# frob:tests python/sadi/doctor/probes.py::RealProbes.os_kind
# frob:tests python/sadi/doctor/probes.py::RealProbes.os_version
# frob:tests python/sadi/doctor/probes.py::RealProbes.plugin_findings
# frob:tests python/sadi/doctor/probes.py::RealProbes.py_version
# frob:tests python/sadi/doctor/probes.py::RealProbes.python_exe
# frob:tests python/sadi/doctor/probes.py::RealProbes.read_text
# frob:tests python/sadi/doctor/probes.py::RealProbes.readlink
# frob:tests python/sadi/doctor/probes.py::RealProbes.requires_python
# frob:tests python/sadi/doctor/probes.py::RealProbes.run
# frob:tests python/sadi/doctor/probes.py::RealProbes.spill_files
# frob:tests python/sadi/doctor/probes.py::RealProbes.user_data_dir
# frob:tests python/sadi/doctor/probes.py::RealProbes.user_groups
# frob:tests python/sadi/doctor/probes.py::RealProbes.web_bundle
# frob:tests python/sadi/doctor/probes.py::RealProbes.which
# frob:tests python/sadi/doctor/probes.py::RealProbes.writable
def test_real_probes_full_run_is_valid() -> None:
    """Every check runs against the real machine without crashing and yields a valid report."""
    report = doctor.run(RunOptions()).unwrap()
    assert len(report.results) == len(list(all_checks()))
    assert DoctorReport.model_validate_json(report.model_dump_json()) == report
    assert doctor.exit_code(report) in (0, 1, 2)
