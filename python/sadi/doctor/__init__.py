"""sadi doctor: read-only environment checks with numbered, per-OS remediation steps."""

# frob:ticket 01M6WA9WYE9D71BBA7AV3H5CGF
# frob:ticket 01M6WJHW2KET2M1730MZVJ1X4E
from __future__ import annotations

import hashlib
import platform
import time
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime

from typani import Err, Ok, Result

from sadi.doctor.probes import Probes, RealProbes
from sadi.doctor.registry import CheckFn, Ctx, Outcome, all_checks, get_remedy
from sadi.doctor.runner import Abort, Budget, schedule
from sadi.doctor.schema import (
    CheckResult,
    CheckSpec,
    DoctorError,
    DoctorReport,
    Evidence,
    Host,
    Layer,
    Os,
    ProbeError,
    Remediation,
    RunOptions,
    Severity,
    SkipReason,
    Status,
    Summary,
)
from sadi.doctor.steps import manual, verify
from sadi.logging_setup import get_logger

_log = get_logger(__name__)

__all__ = ["Budget", "resolve_data_root", "run", "exit_code"]


def resolve_data_root(options: RunOptions, probes: Probes) -> str:
    """Pick the data root: --data-root, then SADI_DATA_ROOT, then the per-user default."""
    return options.data_root or probes.env().get("SADI_DATA_ROOT") or probes.user_data_dir()


def _select(options: RunOptions) -> Result[list[tuple[CheckSpec, CheckFn]], DoctorError]:
    """Apply --check/--layer/--skip to the catalog, validating ids."""
    catalog = all_checks()
    known = {spec.id for spec, _ in catalog}
    for wanted in (*(options.checks or ()), *options.skip):
        if wanted not in known:
            _log.error("unknown check id %s", wanted)
            return Err(DoctorError.UnknownCheck)
    chosen = [
        (spec, fn)
        for spec, fn in catalog
        if (options.checks is None or spec.id in options.checks)
        and (options.layers is None or spec.layer in options.layers)
        and spec.id not in options.skip
    ]
    return Ok(chosen)


def _build_remediation(
    spec: CheckSpec, outcome: Outcome, ctx: Ctx
) -> tuple[Remediation | None, ProbeError | None]:
    """Build the per-OS remediation for a warn/fail outcome, appending the verify step."""
    assert outcome.mode is not None
    fn = get_remedy(spec.id, outcome.mode)
    if fn is None:
        _log.error("no remedy for %s/%s", spec.id, outcome.mode)
        return None, ProbeError(kind="exception", detail=f"no remedy for {spec.id}/{outcome.mode}")
    fix = fn(ctx, outcome)
    return (
        Remediation(
            check_id=spec.id,
            mode=outcome.mode,
            os=ctx.os,
            summary=fix.summary,
            steps=(*fix.steps, verify(spec.id, ctx.os)),
            docs=fix.docs,
        ),
        None,
    )


def _execute(spec: CheckSpec, fn: CheckFn, ctx: Ctx) -> CheckResult:
    """Run one check; probe errors and escaped exceptions become a probe-error fail."""
    started = time.monotonic()
    error: ProbeError | None = None
    try:
        outcome = fn(ctx)
    except Exception as exc:  # noqa: BLE001 - a crashing check must not end the run
        _log.exception("check %s crashed", spec.id)
        error = ProbeError(kind="exception", detail=f"{type(exc).__name__}: {exc}")
        outcome = Outcome(Status.FAIL, f"Check crashed: {exc}", mode="probe-error")
    remediation = None
    if outcome.status in (Status.WARN, Status.FAIL):
        if outcome.mode == "probe-error":
            error = error or ProbeError(kind="exception", detail=outcome.headline)
            remediation = _probe_error_remediation(spec, ctx)
        else:
            try:
                remediation, error = _build_remediation(spec, outcome, ctx)
            except Exception as exc:  # noqa: BLE001
                _log.exception("remedy for %s crashed", spec.id)
                error = ProbeError(kind="exception", detail=f"remedy: {exc}")
            if remediation is None:
                remediation = _probe_error_remediation(spec, ctx)
                outcome = Outcome(
                    Status.FAIL, outcome.headline, mode="probe-error", facts=outcome.facts
                )
    duration = int((time.monotonic() - started) * 1000)
    _log.info("%s %s (%s) in %d ms", spec.id, outcome.status.value, outcome.mode, duration)
    return CheckResult(
        id=spec.id,
        title=spec.title,
        layer=spec.layer,
        severity=spec.severity,
        status=outcome.status,
        headline=outcome.headline,
        mode=outcome.mode,
        skip_reason=outcome.skip_reason,
        evidence=Evidence(facts=dict(outcome.facts), commands_run=outcome.commands, error=error),
        remediation=remediation,
        duration_ms=duration,
    )


def _probe_error_remediation(spec: CheckSpec, ctx: Ctx) -> Remediation:
    """Generic remedy when a check itself could not run to completion."""
    return Remediation(
        check_id=spec.id,
        mode="probe-error",
        os=ctx.os,
        summary="The check could not complete",
        steps=(
            manual(
                "Re-run with logging to see the cause: set SADI_LOG_LEVEL=DEBUG and repeat.",
                "The log names the probe that failed.",
                if_not="File the log with the report; this is a doctor bug, not a problem with your setup.",
            ),
            verify(spec.id, ctx.os),
        ),
    )


def _skipped(spec: CheckSpec, reason: SkipReason, headline: str) -> CheckResult:
    """Build a SKIP result without running the check."""
    return CheckResult(
        id=spec.id,
        title=spec.title,
        layer=spec.layer,
        severity=spec.severity,
        status=Status.SKIP,
        headline=headline,
        skip_reason=reason,
        evidence=Evidence(),
        duration_ms=0,
    )


def _gate(
    spec: CheckSpec, options: RunOptions, os: Os, done: Mapping[str, CheckResult]
) -> CheckResult | None:
    """Return a SKIP for a check that must not run (wrong OS, opt-in, failed prerequisite)."""
    if os not in spec.applies_to:
        return _skipped(spec, SkipReason.NOT_APPLICABLE_OS, f"Not applicable on {os.value}")
    if spec.opt_in_flag and not getattr(options, spec.opt_in_flag, False):
        return _skipped(spec, SkipReason.OPT_IN, f"Needs --{spec.opt_in_flag.replace('_', '-')}")
    blocker = next(
        (
            d
            for d in spec.depends_on
            if d in done
            and (
                done[d].status is Status.FAIL
                or done[d].skip_reason in (SkipReason.PREREQUISITE_FAILED, SkipReason.TIMEOUT)
            )
        ),
        None,
    )
    if blocker:
        return _skipped(spec, SkipReason.PREREQUISITE_FAILED, f"Skipped because {blocker} failed")
    return None


def _timed_out(spec: CheckSpec, ctx: Ctx, why: Abort) -> CheckResult:
    """Build the UNVERIFIED (skip/timeout) result, with a remedy, for a check that did not finish."""
    headline = {
        "check-timeout": "Check timed out, so this is unverified",
        "run-timeout": "Run time budget ran out before this check finished, so it is unverified",
        "crashed": "Check worker crashed, so this is unverified",
    }[why]
    remediation = Remediation(
        check_id=spec.id,
        mode="timeout",
        os=ctx.os,
        summary="The check did not finish in time",
        steps=(
            manual(
                f"Re-run only this check: sadi-doctor --check {spec.id}",
                "It finishes and reports pass, warn or fail.",
                if_not="Look for a hung device, drive or antivirus scan, then retry.",
            ),
            verify(spec.id, ctx.os),
        ),
    )
    _log.warning("%s unverified: %s", spec.id, why)
    return CheckResult(
        id=spec.id,
        title=spec.title,
        layer=spec.layer,
        severity=spec.severity,
        status=Status.SKIP,
        headline=headline,
        mode="timeout",
        skip_reason=SkipReason.TIMEOUT,
        evidence=Evidence(error=ProbeError(kind="timeout", detail=why)),
        remediation=remediation,
        duration_ms=0,
    )


def summarize(results: tuple[CheckResult, ...]) -> Summary:
    """Count statuses and derive the verdict and first action."""
    counts = {s: 0 for s in Status}
    for r in results:
        counts[r.status] += 1
    failed = [r for r in results if r.status is Status.FAIL]
    order = list(Severity)
    worst = min((r.severity for r in failed), key=order.index, default=None)
    if worst is Severity.BLOCKER:
        verdict = "blocked"
    elif failed or counts[Status.WARN]:
        verdict = "degraded"
    else:
        verdict = "ready"
    first = next(
        (r for r in (*failed, *(r for r in results if r.status is Status.WARN)) if r.remediation),
        None,
    )
    action = first.remediation.steps[0].text if first and first.remediation else None
    return Summary(counts=counts, worst_severity_failed=worst, verdict=verdict, first_action=action)


def exit_code(report: DoctorReport) -> int:
    """Map a report to the CLI exit code: 2 blocker fail, 1 other fail, else 0."""
    worst = report.summary.worst_severity_failed
    if worst is Severity.BLOCKER:
        return 2
    return 1 if worst is not None else 0


def _host(probes: Probes, os: Os, data_root: str) -> Host:
    """Describe the machine for the report (hostname is hashed)."""
    node = hashlib.sha256(platform.node().encode()).hexdigest()[:12]
    major, minor, micro = probes.py_version()
    return Host(
        os=os,
        os_version=probes.os_version(),
        arch=probes.machine(),
        python=f"{major}.{minor}.{micro}",
        sadi_version=probes.dist_version("sadi") or "unknown",
        sadi_py_version=probes.dist_version("sadi-py") or probes.dist_version("sadi_py"),
        hostname_hash=node,
        data_root=data_root,
        wsl_distro=probes.env().get("WSL_DISTRO_NAME"),
    )


def run(
    options: RunOptions, probes: Probes | None = None, budget: Budget | None = None
) -> Result[DoctorReport, DoctorError]:
    """Run the selected checks in parallel (deps first, time-boxed); report in catalog order."""
    probes = probes or RealProbes()
    selected = _select(options)
    if selected.is_err:
        return Err(selected.err)
    chosen = selected.unwrap()
    started_at = datetime.now(UTC)
    os = options.render_os or probes.os_kind()
    data_root = resolve_data_root(options, probes)
    ctx = Ctx(probes=probes, options=options, os=os, data_root=data_root)
    _log.info("doctor run: %d checks on %s, data root %s", len(chosen), os.value, data_root)
    specs = {spec.id: (spec, fn) for spec, fn in chosen}

    def work(ident: str) -> CheckResult:
        spec, fn = specs[ident]
        return _execute(spec, fn, ctx)

    def gate(ident: str, done: Mapping[str, CheckResult]) -> CheckResult | None:
        return _gate(specs[ident][0], options, os, done)

    def aborted(ident: str, why: Abort) -> CheckResult:
        return _timed_out(specs[ident][0], ctx, why)

    done = schedule(
        [spec.id for spec, _ in chosen],
        {spec.id: spec.depends_on for spec, _ in chosen},
        work,
        gate,
        aborted,
        budget or Budget.for_deep(options.deep),
    )
    results = tuple(done[spec.id] for spec, _ in chosen)
    report = DoctorReport(
        run_id=uuid.uuid4(),
        started_at=started_at,
        finished_at=datetime.now(UTC),
        host=_host(probes, os, data_root),
        options=options,
        results=results,
        summary=summarize(results),
    )
    _log.info("doctor verdict: %s", report.summary.verdict)
    return Ok(report)


_ = Layer  # re-exported for callers building RunOptions
