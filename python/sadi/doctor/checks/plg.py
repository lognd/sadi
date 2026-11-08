"""PLG checks: wrap the plugin doctor so its findings share the doctor's report and remedy shape."""

# frob:ticket 01M6WA9WYE9D71BBA7AV3H5CGF
from __future__ import annotations

import re

from sadi.doctor.registry import Ctx, Fix, Outcome, check, fail, ok, remedy, warn
from sadi.doctor.schema import Layer, Severity
from sadi.doctor.steps import manual

_NUMBER = re.compile(r"^\d+\.\s*")
_MAX_STEPS = 6


@check(
    "PLG-010",
    Layer.PLG,
    "Plugins load cleanly",
    Severity.WARNING,
    {
        "plugin-error": "At least one plugin has an error finding",
        "plugin-warning": "Plugins have warnings only",
    },
    "sadi.plugins.doctor.check_plugins over the standard plugin sources",
)
def plg_010(ctx: Ctx) -> Outcome:
    """Run the plugin doctor and fold its findings into one result."""
    from sadi.plugins.doctor import Severity as FindingSeverity  # lazy: keeps sadi.store out

    findings = [f for f in ctx.probes.plugin_findings() if f.severity is not FindingSeverity.INFO]
    if not findings:
        return ok("No plugin problems")
    worst = next((f for f in findings if f.severity is FindingSeverity.ERROR), findings[0])
    facts = {
        "codes": [f"{f.plugin_id}:{f.code}" for f in findings],
        "first_plugin": worst.plugin_id,
        "first_message": worst.message,
        "first_fixes": [_NUMBER.sub("", s) for s in worst.fixes],
    }
    headline = f"{worst.plugin_id}: {worst.message}"
    if worst.severity is FindingSeverity.ERROR:
        return fail("plugin-error", headline, **facts)
    return warn("plugin-warning", headline, **facts)


def _plugin_fix(ctx: Ctx, out: Outcome) -> Fix:
    """Turn the plugin doctor's numbered fixes into manual steps."""
    fixes = out.facts.get("first_fixes")
    texts = list(fixes) if isinstance(fixes, list) else []
    plugin = out.facts.get("first_plugin", "the plugin")
    if not texts:
        texts = [f"Read `sadi plugins doctor` output for {plugin}."]
    steps = tuple(
        manual(t, "The plugin doctor no longer lists this finding.") for t in texts[:_MAX_STEPS]
    )
    return Fix(f"Fix plugin {plugin}", steps)


remedy("PLG-010", "plugin-error")(_plugin_fix)
remedy("PLG-010", "plugin-warning")(_plugin_fix)
