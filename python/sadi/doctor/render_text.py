"""Plain ASCII rendering of a DoctorReport: one line per check, numbered fix steps for problems."""

# frob:ticket 01M6WA9WYE9D71BBA7AV3H5CGF
from __future__ import annotations

import textwrap

from sadi.doctor.schema import CheckResult, DoctorReport, Shell, Status, Step

WIDTH = 80
_TAG = {Status.PASS: "PASS", Status.WARN: "WARN", Status.FAIL: "FAIL", Status.SKIP: "SKIP"}
_PROMPT = {Shell.SH: "$", Shell.POWERSHELL: "PS>", Shell.CMD: ">"}


def _wrap(text: str, indent: str, first: str | None = None) -> list[str]:
    """Wrap text to WIDTH with a hanging indent."""
    return textwrap.wrap(
        text, WIDTH, initial_indent=first if first is not None else indent, subsequent_indent=indent
    ) or [indent.rstrip()]


def _step_lines(n: int, step: Step) -> list[str]:
    """Render one numbered step with its commands and Expect/Changes/If not lines."""
    pad = "      "
    lines = _wrap(step.text, pad, f"  {n}. ")
    for c in step.commands:
        ctx = f"  ({c.context})" if c.context else ""
        lines.append(f"{pad}{_PROMPT[c.shell]} {c.line}{ctx}")
    lines += _wrap(f"Expect: {step.expect}", pad)
    if step.changes:
        lines += _wrap(f"Changes: {step.changes}", pad)
    if step.if_not:
        lines += _wrap(f"If not: {step.if_not}", pad)
    if step.alt:
        lines += _wrap(f"Or: {step.alt}", pad)
    return lines


def render_result(r: CheckResult) -> list[str]:
    """Render one check result; problems include the full remediation."""
    lines = [f"[{_TAG[r.status]}] {r.id}  {r.headline}"]
    if r.remediation:
        lines.append(f"  Fix: {r.remediation.summary} ({r.remediation.os.value})")
        for i, step in enumerate(r.remediation.steps, 1):
            lines += _step_lines(i, step)
    return lines


def render(report: DoctorReport, *, verbose: bool = False) -> str:
    """Render the whole report as ASCII text; skips and passes are one line each."""
    h = report.host
    out = [
        f"SADI doctor - {h.os.value} ({h.os_version}), Python {h.python}, sadi {h.sadi_version}",
        f"Data root: {h.data_root}",
        "",
    ]
    for r in report.results:
        if r.status is Status.PASS and not verbose:
            out.append(f"[PASS] {r.id}  {r.headline}")
        else:
            out += render_result(r)
    c = report.summary.counts
    out += [
        "",
        f"{c.get(Status.PASS, 0)} passed, {c.get(Status.WARN, 0)} warnings, "
        f"{c.get(Status.FAIL, 0)} failed, {c.get(Status.SKIP, 0)} skipped. "
        f"Verdict: {report.summary.verdict}.",
    ]
    if report.summary.first_action:
        out += _wrap(f"Start with: {report.summary.first_action}", "  ")
    text = "\n".join(out) + "\n"
    return text.encode("ascii", "replace").decode("ascii")
