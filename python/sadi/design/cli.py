"""Command-line weight planner: type your weights and wire, get the hang order (advisory)."""

# Usage: python -m sadi.design.cli --weights 1,1,2,2,5 --diameter 2.019e-4 \
#   --length 0.5 --cal-points 0.001:0.05,0.002:0.11,... [--u-mass 0.01] [--captured 1:0.5,3:1.4] [--hangs 5]

# frob:ticket 01M72ZGDCC7C75SMXSJRH6VBAE

from __future__ import annotations

import argparse
import logging
import sys

from pydantic import ValidationError
from typani import Err, Ok, Result

from sadi.design.cal_fit import Calibration, resolve_calibration
from sadi.design.height_plan import HeightPlan, parse_heights, plan_heights
from sadi.design.models import CapturedPoint, PlanRequest, Weight
from sadi.design.plan import plan
from sadi.labs.lctt.loading import STANDARD_G
from sadi.logging_setup import get_logger

__all__ = ["build_request", "format_height_plan", "main", "parse_captured", "parse_weights"]

_log = get_logger(__name__)


def parse_weights(text: str, u_mass: float) -> Result[list[Weight], str]:
    """Parse 'kg' or 'kg:u' items into weights w1, w2, ...; a missing u falls back to u_mass; duplicates stay distinct."""
    parts = [t.strip() for t in text.replace(";", ",").replace("\n", ",").split(",")]
    out: list[Weight] = []
    for i, part in enumerate(p for p in parts if p):
        try:
            f = part.split(":")
            if len(f) not in (1, 2):
                raise ValueError("expected kg or kg:uncertainty")
            u = float(f[1]) if len(f) == 2 and f[1].strip() else u_mass
            out.append(Weight(weight_id=f"w{i + 1}", mass_kg=float(f[0]), u_mass_kg=u))
        except (ValueError, ValidationError) as exc:
            _log.warning("bad weight %r: %s", part, exc)
            return Err(f"Could not read weight {part!r} (use kg or kg:u_kg): {exc}")
    return Ok(out)


def parse_captured(text: str) -> Result[list[CapturedPoint], str]:
    """Parse 'N:volts,N:volts' (newtons) into already-captured points for replanning."""
    out: list[CapturedPoint] = []
    for part in filter(None, (t.strip() for t in text.replace("\n", ",").split(","))):
        try:
            newtons, volts = part.split(":")
            out.append(CapturedPoint(mass_kg=float(newtons) / STANDARD_G, volts=float(volts)))
        except (ValueError, ValidationError) as exc:
            _log.warning("bad captured point %r: %s", part, exc)
            return Err(f"Could not read captured point {part!r} (use N:volts): {exc}")
    return Ok(out)


def build_request(
    *,
    weights: str,
    u_mass: float,
    diameter: float,
    u_diameter: float,
    length: float,
    u_length: float,
    cal: Calibration,
    saturation: float | None,
    captured: str,
    max_hangs: int | None = None,
) -> Result[PlanRequest, str]:
    """Build a PlanRequest from text fields; shared by the CLI and the browser planner."""
    ws = parse_weights(weights, u_mass)
    if isinstance(ws, Err):
        return ws
    cs = parse_captured(captured)
    if isinstance(cs, Err):
        return cs
    try:
        return Ok(
            PlanRequest(
                weights=tuple(ws.value), diameter_m=diameter, u_diameter_m=u_diameter,
                length_m=length, u_length_m=u_length,
                cal_slope_v_per_m=cal.slope_v_per_m, cal_offset_v=cal.offset_v,
                u_cal_slope_v_per_m=cal.se_slope, u_cal_offset_v=cal.se_offset, cal_cov=cal.cov,
                saturation_v=saturation, captured=tuple(cs.value),
                config=PlanConfig(max_hangs=max_hangs),
            )
        )
    except ValidationError as exc:
        _log.warning("invalid plan request: %s", exc)
        return Err(f"Invalid value: {exc.errors()[0]['loc']}: {exc.errors()[0]['msg']}")


# frob:ticket 01M7305JYQ6AZA2Z92Y5QQ54BF
def format_height_plan(p: HeightPlan) -> str:
    """Render a height plan as the operator-facing table (shared with tests)."""
    lines = [
        f"inventory={p.n_inventory} usable={p.n_usable} dropped(sat={p.dropped_saturation}) "
        f"slope se={p.se_slope_v_per_m} V/m intercept se={p.se_offset_v} V (design estimate)",
        "#  id     height_m   u_height_m  pred_V   slope_se   offset_se",
    ]
    for h in p.steps:
        ses = "-" if h.se_slope_v_per_m is None else f"{h.se_slope_v_per_m:.4g}"
        seo = "-" if h.se_offset_v is None else f"{h.se_offset_v:.4g}"
        lines.append(
            f"{h.order:<2} {h.height_id:<6} {h.height_m:<10.6g} {h.u_height_m:<11.3g} "
            f"{h.predicted_volts:7.3f}  {ses:<9}  {seo}"
        )
    return "\n".join(lines) + "\n"


def _run_heights(args: argparse.Namespace) -> HeightPlan | None:
    """Plan which gauge heights to use first; None (after printing why) when no plan exists."""
    if args.cal_slope is None:
        sys.stdout.write("No plan: --heights needs --cal-slope (nominal V per m) to turn height into volts\n")
        return None
    hs = parse_heights(args.heights)
    if isinstance(hs, Err):
        sys.stdout.write(f"No plan: {hs.error}\n")
        return None
    res = plan_heights(
        hs.value, nominal_slope_v_per_m=args.cal_slope, nominal_offset_v=args.cal_offset,
        saturation_v=args.saturation,
    )
    if isinstance(res, Err):
        sys.stdout.write(f"No plan: {res.error}\n")
        return None
    sys.stdout.write("1. Heights to use\n" + format_height_plan(res.value))
    return res.value


def main(argv: list[str] | None = None) -> int:
    """Print the planned hang order as a table; non-zero exit when no plan exists."""
    ap = argparse.ArgumentParser(description="Plan which weights to hang, in order.")
    ap.add_argument("--heights", default="",
                    help="height inventory h:u,... (m); plans which heights to calibrate with (needs --cal-slope)")
    ap.add_argument("--weights", default="", help="comma list of weight masses in kg, e.g. 0.1,0.1,0.2")
    ap.add_argument("--u-mass", type=float, default=0.0, help="mass uncertainty per weight, kg")
    ap.add_argument("--diameter", type=float, default=2.019e-4, help="wire diameter, m")
    ap.add_argument("--u-diameter", type=float, default=0.0, help="diameter uncertainty, m")
    ap.add_argument("--length", type=float, default=None, help="gauge length L0, m")
    ap.add_argument("--u-length", type=float, default=0.0, help="L0 uncertainty, m")
    ap.add_argument("--cal-points", default="", help="calibration points height_m:volts,... (>= 3; fitted)")
    ap.add_argument("--cal-slope", type=float, default=None,
                    help="OVERRIDE: typed LVDT slope, V per m (skips the fit; no uncertainty)")
    ap.add_argument("--cal-offset", type=float, default=0.0, help="OVERRIDE offset, V (with --cal-slope only)")
    ap.add_argument("--saturation", type=float, default=None, help="saturation limit, V")
    ap.add_argument("--captured", default="", help="already-hung points to replan from: N:volts,N:volts")
    ap.add_argument("--hangs", type=int, default=None, help="number of hangs wanted; omit for the advisory early stop")
    args = ap.parse_args(argv)
    logging.getLogger("sadi").setLevel(logging.WARNING)  # keep the table readable; errors still show
    logging.getLogger("plan").setLevel(logging.WARNING)
    logging.getLogger("design").setLevel(logging.WARNING)
    hplan: HeightPlan | None = None
    if args.heights.strip():
        hplan = _run_heights(args)
        if hplan is None:
            return 1
        if not args.weights.strip():
            return 0
        sys.stdout.write("2. Recommended weights (GP selection)\n")
    if not args.weights.strip() or args.length is None:
        sys.stdout.write("No plan: give --weights and --length (or --heights)\n")
        return 1
    # frob:ticket 01M7301MDWNXK9Z0D8TBDBNP4G
    cal = resolve_calibration(args.cal_points, args.cal_slope, args.cal_offset)
    if isinstance(cal, Err):
        sys.stdout.write(f"No plan: {cal.error}\n")
        return 1
    cal_v = cal.value
    if hplan is not None and cal_v.source == "override":
        cal_v = cal_v.model_copy(update={"se_slope": hplan.se_slope_v_per_m or 0.0, "se_offset": hplan.se_offset_v or 0.0})
        _log.info("weight plan uses height-plan design uncertainty")
        sys.stdout.write("note: the slope uncertainty below is the height plan's design estimate\n")
    sys.stdout.write(cal_v.summary() + "\n")
    built = build_request(
        weights=args.weights, u_mass=args.u_mass, diameter=args.diameter, u_diameter=args.u_diameter,
        length=args.length, u_length=args.u_length, cal=cal_v, saturation=args.saturation, captured=args.captured,
    )
    if isinstance(built, Err):
        sys.stdout.write(f"No plan: {built.error}\n")
        return 1
    req = built.value
    res = plan(req)
    if isinstance(res, Err):
        sys.stdout.write(f"No plan: {res.error}\n")
        _log.error("no plan: %s", res.error)
        return 1
    p = res.value
    sys.stdout.write(
        f"phase={p.phase} inventory={p.n_inventory} achievable={p.n_achievable} usable={p.n_usable} "
        f"dropped(sat={p.dropped_saturation}, capacity={p.dropped_capacity})\n"
    )
    sys.stdout.write("#  n  hang (weights)            tension_N  pred_V   +/-V     reason\n")
    for h in p.hangs:
        sys.stdout.write(
            f"{h.order:<2} {len(h.weight_ids):<2} {'+'.join(h.weight_ids):<24} {h.tension_n:9.3f}  "
            f"{h.predicted_volts:7.3f}  {h.u_predicted_volts:6.3f}  {h.reason}\n"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
