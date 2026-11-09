"""WEB-010 / DATA-010 remediation text is concrete, honors the data root and never auto-runs."""

# frob:ticket 01M6Z4H8GRP83B32G68N220D8K
from __future__ import annotations

from doctor_fakes import FakeProbes, healthy

import sadi.doctor as doctor
import sadi.doctor.fix as fixmod
from sadi.doctor.schema import CheckResult, Os, RunOptions, StepKind


def _result(p: FakeProbes, check_id: str, root: str | None = None) -> CheckResult:
    """Run one check against fake probes and return its result."""
    opts = RunOptions(checks=(check_id,), data_root=root)
    return doctor.run(opts, p).unwrap().results[0]


def _lines(res: CheckResult) -> list[str]:
    """All command lines of a result's remediation."""
    assert res.remediation is not None
    return [c.line for s in res.remediation.steps for c in s.commands]


# frob:tests python/sadi/doctor/checks/web.py::web_010
def test_web_010_points_at_build_script() -> None:
    """A missing bundle yields the packaging build command and names sadi/_ui."""
    p = healthy()
    p.web_bundle = lambda: (False, 0)  # type: ignore[method-assign]
    res = _result(p, "WEB-010")
    assert res.status.value == "fail"
    assert "python packaging/build_ui.py" in _lines(res)
    assert res.remediation is not None
    text = " ".join(s.expect or "" for s in res.remediation.steps)
    assert "sadi/_ui/index.html" in text
    assert res.remediation.steps[-1].kind is StepKind.VERIFY


# frob:tests python/sadi/doctor/checks/data.py::data_010
def test_data_010_missing_honors_configured_root() -> None:
    """The mkdir command targets the configured root, is owner-only and never recursive-deletes."""
    p = healthy()
    p.os = Os.LINUX
    p.dirs.pop(p.data_dir)
    res = _result(p, "DATA-010", "/srv/sadi-data")
    lines = _lines(res)
    assert "mkdir -p -m 700 '/srv/sadi-data'" in lines
    assert not any("rm " in ln for ln in lines)


# frob:tests python/sadi/doctor/fix.py::plan
def test_fix_never_plans_install_or_data_dir_steps() -> None:
    """Doctor stays read-only: the build and mkdir steps are never auto-applied."""
    p = healthy()
    p.web_bundle = lambda: (False, 0)  # type: ignore[method-assign]
    assert fixmod.plan(_result(p, "WEB-010"), None) == []
    q = healthy()
    q.dirs.pop(q.data_dir)
    assert fixmod.plan(_result(q, "DATA-010"), None) == []
