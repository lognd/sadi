"""Command-line weight planner: type your weights and wire, get the hang order (advisory)."""

# Usage: python -m sadi.design.cli --weights 0.1,0.1,0.2,0.2,0.5 --diameter 2.019e-4 \
#   --length 0.5 --cal-slope 12.0 [--u-mass 1e-4] [--captured 0.1:0.5,0.3:1.4]

# frob:ticket 01M72ZGDCC7C75SMXSJRH6VBAE

from __future__ import annotations

import argparse
import logging
import sys

from pydantic import ValidationError
from typani import Err, Ok, Result

from sadi.design.models import CapturedPoint, PlanRequest, Weight
from sadi.design.plan import plan
from sadi.logging_setup import get_logger

__all__ = ["build_request", "main", "parse_captured", "parse_weights"]

_log = get_logger(__name__)


def parse_weights(text: str, u_mass: float) -> Result[list[Weight], str]:
    """Parse '0.1,0.2' (kg) into weights w1, w2, ...; duplicates stay distinct ids."""
    parts = [t.strip() for t in text.replace(";", ",").replace("\n", ",").split(",")]
    parts = [t for t in parts if t]
    try:
        return Ok([Weight(weight_id=f"w{i + 1}", mass_kg=float(t), u_mass_kg=u_mass) for i, t in enumerate(parts)])
    except (ValueError, ValidationError) as exc:
        _log.warning("bad weights %r: %s", text, exc)
        return Err(f"Could not read the weights list (use kg separated by commas): {exc}")


def parse_captured(text: str) -> Result[list[CapturedPoint], str]:
    """Parse 'kg:volts,kg:volts' into already-captured points for replanning."""
    out: list[CapturedPoint] = []
    for part in filter(None, (t.strip() for t in text.replace("\n", ",").split(","))):
        try:
            kg, volts = part.split(":")
            out.append(CapturedPoint(mass_kg=float(kg), volts=float(volts)))
        except (ValueError, ValidationError) as exc:
            _log.warning("bad captured point %r: %s", part, exc)
            return Err(f"Could not read captured point {part!r} (use kg:volts): {exc}")
    return Ok(out)


def build_request(
    *,
    weights: str,
    u_mass: float,
    diameter: float,
    u_diameter: float,
    length: float,
    u_length: float,
    cal_slope: float,
    cal_offset: float,
    saturation: float | None,
    captured: str,
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
                cal_slope_v_per_m=cal_slope, cal_offset_v=cal_offset,
                saturation_v=saturation, captured=tuple(cs.value),
            )
        )
    except ValidationError as exc:
        _log.warning("invalid plan request: %s", exc)
        return Err(f"Invalid value: {exc.errors()[0]['loc']}: {exc.errors()[0]['msg']}")


def main(argv: list[str] | None = None) -> int:
    """Print the planned hang order as a table; non-zero exit when no plan exists."""
    ap = argparse.ArgumentParser(description="Plan which weights to hang, in order.")
    ap.add_argument("--weights", required=True, help="comma list of weight masses in kg, e.g. 0.1,0.1,0.2")
    ap.add_argument("--u-mass", type=float, default=0.0, help="mass uncertainty per weight, kg")
    ap.add_argument("--diameter", type=float, default=2.019e-4, help="wire diameter, m")
    ap.add_argument("--u-diameter", type=float, default=0.0, help="diameter uncertainty, m")
    ap.add_argument("--length", type=float, required=True, help="gauge length L0, m")
    ap.add_argument("--u-length", type=float, default=0.0, help="L0 uncertainty, m")
    ap.add_argument("--cal-slope", type=float, required=True, help="LVDT calibration slope, V per m")
    ap.add_argument("--cal-offset", type=float, default=0.0, help="LVDT calibration offset, V")
    ap.add_argument("--saturation", type=float, default=None, help="saturation limit, V")
    ap.add_argument("--captured", default="", help="already-hung points to replan from: kg:volts,kg:volts")
    args = ap.parse_args(argv)
    logging.getLogger("sadi").setLevel(logging.WARNING)  # keep the table readable; errors still show
    logging.getLogger("plan").setLevel(logging.WARNING)
    logging.getLogger("design").setLevel(logging.WARNING)
    built = build_request(
        weights=args.weights, u_mass=args.u_mass, diameter=args.diameter, u_diameter=args.u_diameter,
        length=args.length, u_length=args.u_length, cal_slope=args.cal_slope,
        cal_offset=args.cal_offset, saturation=args.saturation, captured=args.captured,
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
    sys.stdout.write("#  hang (weights)            total_kg  tension_N  pred_V   +/-V     reason\n")
    for h in p.hangs:
        sys.stdout.write(
            f"{h.order:<2} {'+'.join(h.weight_ids):<24} {h.total_mass_kg:8.4f}  {h.tension_n:8.3f}  "
            f"{h.predicted_volts:7.3f}  {h.u_predicted_volts:6.3f}  {h.reason}\n"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
