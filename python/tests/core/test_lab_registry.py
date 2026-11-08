"""Tests for sadi.core.lab, sadi.core.registry and the lab import boundary."""

# frob:ticket 01M6W7R1G903HZ7V7JRCYC6ZT7

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError
from typani import Err, Ok, Result

from sadi.core import registry as registry_mod
from sadi.core.errors import ComputeError, InputCode
from sadi.core.lab import (
    AnalysisResult,
    CaptureKind,
    ExportFormat,
    ExportFormatId,
    LabId,
    LabModule,
    StepId,
    StepSpec,
    needs_device,
)
from sadi.core.models import CapturedPoint, Phase, RunState
from sadi.core.registry import LabRegistry, validate_lab

LABS_DIR = Path(__file__).resolve().parents[2] / "sadi" / "labs"
ALLOWED_PREFIXES = ("sadi.core", "sadi.uncertainty", "sadi.logging_setup")


def _step(sid: str = "s1") -> StepSpec:
    return StepSpec(
        id=StepId(sid),
        title="Step",
        phase=Phase.ELASTIC,
        capture=CaptureKind.DEVICE_POINTS,
        guidance=lambda run: "hint",
    )


def _writer(run: RunState, result: AnalysisResult) -> Result[bytes, ComputeError]:
    return Ok(b"x")


class FakeLab:
    """Minimal LabModule used as the test double."""

    def __init__(
        self,
        lab_id: str = "fake",
        steps: list[StepSpec] | None = None,
        formats: tuple[ExportFormat, ...] = (),
    ) -> None:
        self.id = LabId(lab_id)
        self.title = "Fake"
        self.models: tuple[type[BaseModel], ...] = ()
        self.export_formats = formats
        self._steps = [_step()] if steps is None else steps

    def steps(self) -> list[StepSpec]:
        return self._steps

    def recompute(self, points: tuple[CapturedPoint, ...]) -> Result[AnalysisResult, ComputeError]:
        return Ok(AnalysisResult(values={}))


def _fmt(fid: str) -> ExportFormat:
    return ExportFormat(id=ExportFormatId(fid), title="T", media_type="text/csv", writer=_writer)


# frob:tests python/sadi/core/lab.py::needs_device
def test_needs_device_covers_every_kind() -> None:
    assert {k: needs_device(k) for k in CaptureKind} == {
        CaptureKind.NONE: False,
        CaptureKind.DEVICE_POINTS: True,
        CaptureKind.OPERATOR_INPUT: False,
    }


# frob:tests python/sadi/core/lab.py::StepSpec
def test_stepspec_is_frozen_and_typed() -> None:
    step = _step()
    with pytest.raises(ValidationError):
        step.title = "x"  # ty: ignore[invalid-assignment]
    with pytest.raises(ValidationError):
        StepSpec(
            id=StepId("a"),
            title="",
            phase=Phase.ELASTIC,
            capture=CaptureKind.NONE,
            guidance=lambda r: "",
        )
    with pytest.raises(ValidationError):
        StepSpec(
            id=StepId("a"), title="t", phase=Phase.ELASTIC, capture="bogus", guidance=lambda r: ""
        )  # type: ignore[arg-type]


# frob:tests python/sadi/core/lab.py::LabModule
# frob:tests python/sadi/core/lab.py::LabModule.steps
# frob:tests python/sadi/core/lab.py::LabModule.recompute
def test_fake_lab_satisfies_protocol() -> None:
    lab = FakeLab()
    assert isinstance(lab, LabModule)
    assert len(lab.steps()) == 1
    assert isinstance(lab.recompute(()), Ok)


# frob:tests python/sadi/core/registry.py::LabRegistry.__init__
# frob:tests python/sadi/core/registry.py::LabRegistry.register
# frob:tests python/sadi/core/registry.py::LabRegistry.get
# frob:tests python/sadi/core/registry.py::LabRegistry.ids
def test_register_get_and_duplicate() -> None:
    reg = LabRegistry()
    assert isinstance(reg.register(FakeLab()), Ok)
    assert reg.ids() == [LabId("fake")]
    assert isinstance(reg.get(LabId("fake")), Ok)
    dup = reg.register(FakeLab())
    assert isinstance(dup, Err) and dup.error.code is InputCode.DUPLICATE
    unknown = reg.get(LabId("nope"))
    assert isinstance(unknown, Err) and unknown.error.code is InputCode.UNKNOWN_ID


# frob:tests python/sadi/core/registry.py::validate_lab
def test_validate_rejects_malformed_labs() -> None:
    cases: list[tuple[FakeLab, InputCode]] = [
        (FakeLab(lab_id=""), InputCode.MISSING),
        (FakeLab(steps=[]), InputCode.MISSING),
        (FakeLab(steps=[_step("a"), _step("a")]), InputCode.DUPLICATE),
        (FakeLab(formats=(_fmt("csv"), _fmt("csv"))), InputCode.DUPLICATE),
    ]
    for lab, code in cases:
        res = validate_lab(lab)
        assert isinstance(res, Err) and res.error.code is code
    assert isinstance(validate_lab(FakeLab(formats=(_fmt("csv"), _fmt("json")))), Ok)


class _EP:
    def __init__(self, name: str, factory: Any) -> None:
        self.name = name
        self._factory = factory

    def load(self) -> Any:
        return self._factory


# frob:tests python/sadi/core/registry.py::LabRegistry.discover
def test_discover_registers_good_and_reports_bad(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> LabModule:
        raise RuntimeError("bad")

    eps = [
        _EP("good", lambda: FakeLab("good")),
        _EP("boom", boom),
        _EP("notalab", lambda: object()),
        _EP("dup", lambda: FakeLab("good")),
    ]
    monkeypatch.setattr(registry_mod, "entry_points", lambda group: eps)
    reg = LabRegistry()
    errors = reg.discover()
    assert reg.ids() == [LabId("good")]
    assert [e.code for e in errors] == [InputCode.MISSING, InputCode.MISSING, InputCode.DUPLICATE]


def _violations(source: str, lab: str) -> list[str]:
    """Return imports in `source` that a module of lab `lab` may not make."""
    own = f"sadi.labs.{lab}"
    bad: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            mods = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                continue  # relative: stays inside the lab package
            mods = [node.module or ""]
        else:
            continue
        for mod in mods:
            if not mod.startswith("sadi"):
                continue
            public = all(not p.startswith("_") for p in mod.split("."))
            ok = public and (
                mod == own
                or mod.startswith(own + ".")
                or any(mod == p or mod.startswith(p + ".") for p in ALLOWED_PREFIXES)
            )
            if not ok:
                bad.append(mod)
    return bad


def test_checker_flags_forbidden_imports() -> None:
    assert _violations("import sadi.labs.other", "lctt") == ["sadi.labs.other"]
    assert _violations("from sadi.core._private import x", "lctt") == ["sadi.core._private"]
    assert _violations("from sadi import app", "lctt") == ["sadi"]
    ok = "from sadi.core.lab import LabModule\nimport numpy\nfrom . import x"
    assert _violations(ok, "lctt") == []


def test_labs_import_only_core_public_api() -> None:
    offenders: dict[str, list[str]] = {}
    for path in LABS_DIR.glob("*/**/*.py"):
        lab = path.relative_to(LABS_DIR).parts[0]
        bad = _violations(path.read_text(encoding="utf-8"), lab)
        if bad:
            offenders[str(path)] = bad
    assert offenders == {}
