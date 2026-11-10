"""Standalone browser weight planner: a localhost-only page beside LabVIEW (advisory, saves nothing)."""

# Usage: python -m sadi.design.gui [--port N] [--no-browser]

# frob:ticket 01M72ZGDCC7C75SMXSJRH6VBAE

from __future__ import annotations

import argparse
import json
import logging
import math
import socket
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from typani import Err, Ok, Result

from sadi.design.cal_fit import resolve_calibration
from sadi.design.cli import build_request
from sadi.design.height_plan import parse_heights, plan_heights
from sadi.design.plan import plan
from sadi.logging_setup import get_logger

__all__ = ["HOST", "PAGE", "main", "make_server", "plan_from_form"]

_log = get_logger(__name__)

#: Loopback only: the planner is never reachable from another machine.
HOST = "127.0.0.1"
_MAX_BODY = 64 * 1024

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>SADI weight planner</title>
<style>
body{font-family:sans-serif;margin:1.5em;max-width:60em}
label{display:block;margin:.4em 0}
input,textarea{font-family:monospace}
input[type=text]{width:14em}
textarea{width:30em;height:3.5em}
fieldset{margin:1em 0}
table{border-collapse:collapse;margin-top:1em}
td,th{border:1px solid #888;padding:.25em .6em;text-align:right}
td.l,th.l{text-align:left}
.note{background:#ffd;border:1px solid #cc8;padding:.5em}
.err{color:#a00;font-weight:bold}
small{color:#555}
</style></head><body>
<h1>Weight planner</h1>
<p class="note"><b>Advisory only.</b> This suggests which weights to hang and in what order.
Nothing is saved or sent anywhere; it does not talk to the LVDT or to LabVIEW. Re-run it with the
points you have already captured to replan.</p>
<form id="f">
<fieldset><legend>1. Height inventory (which heights you have)</legend>
<table id="hts"><thead><tr><th>Height, mm</th><th>Uncertainty, mm</th></tr></thead><tbody></tbody></table>
<button type="button" id="addheight">Add row</button>
<small>Enter each height you have and its uncertainty, same as the weights; duplicates stay distinct. Needs the LVDT slope below.</small>
</fieldset>
<fieldset><legend>2. LVDT calibration (type it from your LabVIEW, or fit it from points)</legend>
<label>LVDT slope, V per m (from your LabVIEW calibration)
<input type="text" name="cal_slope" value="" placeholder="blank = fit from the points below"></label>
<label>LVDT offset, V <input type="text" name="cal_offset" value="0"></label>
<small>A typed slope is used as given (no uncertainty) and is all the height plan needs. Or leave it blank and fit from points:</small>
<table id="cal"><thead><tr><th>Height, mm</th><th>Volts, V</th></tr></thead><tbody></tbody></table>
<button type="button" id="addrow">Add row</button>
<small>Enter at least 3 points at 2 or more distinct heights; slope, intercept and their uncertainty are fitted. No default is assumed.</small>
<label>Saturation limit, V (blank = built-in default) <input type="text" name="saturation" value=""></label>
</fieldset>
<fieldset><legend>3. Weight inventory (which weights you have; the recommended weights come from this plus the heights)</legend>
<table id="wts"><thead><tr><th>Mass, g</th><th>Uncertainty, g</th></tr></thead><tbody></tbody></table>
<button type="button" id="addweight">Add row</button>
<small>Enter each weight and its uncertainty; repeat a mass for duplicate weights (max 12). A blank uncertainty uses the default below.</small>
<label>Default mass uncertainty, g <input type="text" name="u_mass" value="0.1"></label>
</fieldset>
<fieldset><legend>Wire</legend>
<label>Diameter, m <input type="text" name="diameter" value="0.0002019" required></label>
<label>Diameter uncertainty, m <input type="text" name="u_diameter" value="0"></label>
<label>Gauge length L0, m <input type="text" name="length" value="0.08313" required></label>
<label>L0 uncertainty, m <input type="text" name="u_length" value="0"></label>
</fieldset>
<fieldset><legend>Already captured</legend>
<label>Points as grams:volts, comma separated (blank = none)<br>
<textarea name="captured"></textarea></label>
</fieldset>
<button type="submit">Plan</button>
</form>
<div id="out"></div>
<script>
const out = document.getElementById("out");
const calBody = document.querySelector("#cal tbody");
function addRow(h, v){
  const tr = calBody.insertRow();
  for (const val of [h, v]) { const td = tr.insertCell(); const i = document.createElement("input"); i.type = "text"; i.value = val; td.appendChild(i); }
}
for (let k = 0; k < 4; k++) addRow("", "");
document.getElementById("addrow").addEventListener("click", () => addRow("", ""));
const wtsBody = document.querySelector("#wts tbody");
function addWeight(m, u){
  const tr = wtsBody.insertRow();
  for (const val of [m, u]) { const td = tr.insertCell(); const i = document.createElement("input"); i.type = "text"; i.value = val; td.appendChild(i); }
}
for (const m of ["20","50","50","100","100","200","10","30"]) addWeight(m, "");
document.getElementById("addweight").addEventListener("click", () => addWeight("", ""));
const htsBody = document.querySelector("#hts tbody");
function addHeight(h, u){
  const tr = htsBody.insertRow();
  for (const val of [h, u]) { const td = tr.insertCell(); const i = document.createElement("input"); i.type = "text"; i.value = val; td.appendChild(i); }
}
for (let k = 0; k < 4; k++) addHeight("", "");
document.getElementById("addheight").addEventListener("click", () => addHeight("", ""));
// Operators type grams and millimetres; the server works in SI (kg, m), so convert on the way in and out.
const G_TO_KG = 1e-3, MM_TO_M = 1e-3;
const fix = (x) => Number(Number(x).toPrecision(10));
function scaleNum(t, k){ const x = Number(t); return Number.isFinite(x) && String(t).trim() !== "" ? String(fix(x * k)) : t; }
// "a:b,c" -> scale the first field of each item (and the second too when both is set)
function scaleList(text, k, both){
  return text.split(",").map(it => { const f = it.split(":"); f[0] = scaleNum(f[0], k); if (both && f.length > 1) f[1] = scaleNum(f[1], k); return f.join(":"); }).join(",");
}
function cell(t, cls){const td=document.createElement("td"); if(cls) td.className=cls; td.textContent=t; return td;}
document.getElementById("f").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const body = {};
  for (const [k, v] of new FormData(ev.target).entries()) body[k] = v;
  body.u_mass = scaleNum(body.u_mass, G_TO_KG);
  body.captured = (body.captured || "").trim() ? scaleList(body.captured.replace(/\n/g, ","), G_TO_KG, false) : "";
  const pts = [];
  for (const tr of calBody.rows) { const [h, v] = [...tr.querySelectorAll("input")].map(i => i.value.trim()); if (h || v) pts.push(scaleNum(h, MM_TO_M) + ":" + v); }
  body.cal_points = pts.join(",");
  const wts = [];
  for (const tr of wtsBody.rows) { const [m, u] = [...tr.querySelectorAll("input")].map(i => i.value.trim()); if (m) wts.push(u ? scaleNum(m, G_TO_KG) + ":" + scaleNum(u, G_TO_KG) : scaleNum(m, G_TO_KG)); }
  body.weights = wts.join(",");
  const hts = [];
  for (const tr of htsBody.rows) { const [h, u] = [...tr.querySelectorAll("input")].map(i => i.value.trim()); if (h) hts.push(u ? scaleNum(h, MM_TO_M) + ":" + scaleNum(u, MM_TO_M) : scaleNum(h, MM_TO_M)); }
  body.heights = hts.join(",");
  out.textContent = "Planning...";
  let data;
  try {
    const r = await fetch("/plan", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
    data = await r.json();
  } catch (e) { out.innerHTML = ""; const p = document.createElement("p"); p.className = "err"; p.textContent = "Request failed: " + e; out.appendChild(p); return; }
  out.innerHTML = "";
  if (!data.ok) { const p = document.createElement("p"); p.className = "err"; p.textContent = "No plan: " + data.error; out.appendChild(p); return; }
  const hp = data.height_steps ? data : data.heights_plan;
  if (hp) {
    const c0 = document.createElement("p");
    c0.textContent = "1. Heights to use (design estimate): slope se " + hp.se_slope_v_per_m + " V/m, intercept se " + hp.se_offset_v + " V.";
    out.appendChild(c0);
    const t0 = document.createElement("table");
    const hr0 = t0.insertRow();
    for (const h of ["#", "Id", "Height mm", "u mm", "Predicted V", "Slope se", "Offset se"]) { const th = document.createElement("th"); th.textContent = h; hr0.appendChild(th); }
    for (const h of hp.height_steps) {
      const r = t0.insertRow();
      for (const v of [h.order, h.height_id, fix(h.height_m / MM_TO_M), fix(h.u_height_m / MM_TO_M), h.predicted_volts, h.se_slope_v_per_m, h.se_offset_v]) r.appendChild(cell(v === null ? "-" : v));
    }
    out.appendChild(t0);
    if (data.height_steps) return;
  }
  const s = document.createElement("p");
  s.textContent = (hp ? "2. Recommended weights (GP selection, minimising error). " : "") + "Phase: " + data.phase + ". Inventory loads " + data.n_inventory + ", achievable " + data.n_achievable +
    ", usable " + data.n_usable + ". Dropped: " + data.dropped_saturation + " saturating, " + data.dropped_capacity + " over wire capacity. (Advisory; nothing saved.)";
  out.appendChild(s);
  const c = document.createElement("p"); c.textContent = data.calibration; out.appendChild(c);
  const t = document.createElement("table");
  const hr = t.insertRow();
  for (const h of ["#", "Hang (weights)", "Total g", "Tension N", "Predicted V", "+/- V", "Reason"]) { const th = document.createElement("th"); th.textContent = h; hr.appendChild(th); }
  for (const h of data.hangs) {
    const r = t.insertRow();
    r.appendChild(cell(h.order)); r.appendChild(cell(h.weights, "l")); r.appendChild(cell(fix(h.total_kg / G_TO_KG)));
    r.appendChild(cell(h.tension_n)); r.appendChild(cell(h.predicted_volts)); r.appendChild(cell(h.u_volts));
    r.appendChild(cell(h.reason, "l"));
  }
  out.appendChild(t);
});
</script></body></html>
"""


def _num(form: dict[str, Any], key: str, *, required: bool, default: float | None) -> Result[float | None, str]:
    """Read one numeric form field; a required field with no value is an error, never defaulted."""
    raw = str(form.get(key, "")).strip()
    if not raw:
        if required:
            return Err(f"{key} is required; enter a value (nothing is assumed)")
        return Ok(default)
    try:
        val = float(raw)
    except ValueError:
        return Err(f"{key} is not a number: {raw!r}")
    if not math.isfinite(val):
        return Err(f"{key} must be finite: {raw!r}")
    return Ok(val)


# frob:ticket 01M7305JYQ6AZA2Z92Y5QQ54BF
def _heights_reply(form: dict[str, Any]) -> dict[str, Any]:
    """Plan which gauge heights to use; the override slope is the nominal V per m."""
    slope = _num(form, "cal_slope", required=True, default=None)
    off = _num(form, "cal_offset", required=False, default=0.0)
    sat = _num(form, "saturation", required=False, default=None)
    for got in (slope, off, sat):
        if isinstance(got, Err):
            return {"ok": False, "error": got.error}
    hs = parse_heights(str(form["heights"]))
    if isinstance(hs, Err):
        return {"ok": False, "error": hs.error}
    res = plan_heights(
        hs.value, nominal_slope_v_per_m=slope.value or 0.0, nominal_offset_v=off.value or 0.0,
        saturation_v=sat.value,
    )
    if isinstance(res, Err):
        _log.info("no height plan: %s", res.error)
        return {"ok": False, "error": str(res.error)}
    p = res.value
    return {
        "ok": True, "advisory": True, "calibration": "heights plan (design estimate)",
        "se_slope_v_per_m": p.se_slope_v_per_m, "se_offset_v": p.se_offset_v,
        "n_inventory": p.n_inventory, "n_usable": p.n_usable, "dropped_saturation": p.dropped_saturation,
        "height_steps": [s.model_dump() for s in p.steps],
    }


def plan_from_form(form: dict[str, Any]) -> dict[str, Any]:
    """Turn a submitted form into the JSON reply: {'ok': True, ...plan} or {'ok': False, 'error': msg}.

    The height inventory is planned first; its design slope/offset uncertainty then feeds the weight plan.
    """
    heights: dict[str, Any] | None = None
    if str(form.get("heights", "")).strip():
        heights = _heights_reply(form)
        if not heights["ok"]:
            return heights
        if not str(form.get("weights", "")).strip():
            return heights
    reply = _weights_reply(form, heights)
    if heights is not None and reply["ok"]:
        reply["heights_plan"] = heights
    return reply


def _weights_reply(form: dict[str, Any], heights: dict[str, Any] | None) -> dict[str, Any]:
    """Plan the weights; with a height plan, a typed slope carries that plan's design uncertainty."""
    nums: dict[str, float | None] = {}
    spec = {
        "u_mass": (False, 0.0), "hangs": (False, None), "diameter": (True, None), "u_diameter": (False, 0.0),
        "length": (True, None), "u_length": (False, 0.0), "cal_slope": (False, None),
        "cal_offset": (False, 0.0), "saturation": (False, None),
    }
    for key, (required, default) in spec.items():
        got = _num(form, key, required=required, default=default)
        if isinstance(got, Err):
            return {"ok": False, "error": got.error}
        nums[key] = got.value
    hangs = None
    if nums["hangs"] is not None:
        if nums["hangs"] != int(nums["hangs"]) or nums["hangs"] < 1:
            return {"ok": False, "error": "hangs must be a whole number of at least 1"}
        hangs = int(nums["hangs"])
    # frob:ticket 01M7301MDWNXK9Z0D8TBDBNP4G
    cal = resolve_calibration(str(form.get("cal_points", "")), nums["cal_slope"], nums["cal_offset"] or 0.0)
    if isinstance(cal, Err):
        return {"ok": False, "error": cal.error}
    cal_v = cal.value
    if heights is not None and cal_v.source == "override":
        cal_v = cal_v.model_copy(update={
            "se_slope": float(heights["se_slope_v_per_m"] or 0.0), "se_offset": float(heights["se_offset_v"] or 0.0),
        })
        _log.info("weight plan uses height-plan design uncertainty slope=%g offset=%g", cal_v.se_slope, cal_v.se_offset)
    built = build_request(
        weights=str(form.get("weights", "")), u_mass=nums["u_mass"] or 0.0,
        diameter=nums["diameter"] or 0.0, u_diameter=nums["u_diameter"] or 0.0,
        length=nums["length"] or 0.0, u_length=nums["u_length"] or 0.0,
        cal=cal_v,
        saturation=nums["saturation"], captured=str(form.get("captured", "")),
        max_hangs=hangs,
    )
    if isinstance(built, Err):
        return {"ok": False, "error": built.error}
    res = plan(built.value)
    if isinstance(res, Err):
        _log.info("no plan: %s", res.error)
        return {"ok": False, "error": str(res.error)}
    p = res.value
    return {
        "ok": True,
        "advisory": True,
        "calibration": cal_v.summary(),
        "cal": cal_v.model_dump(),
        "phase": p.phase.value,
        "n_inventory": p.n_inventory,
        "n_achievable": p.n_achievable,
        "n_usable": p.n_usable,
        "dropped_saturation": p.dropped_saturation,
        "dropped_capacity": p.dropped_capacity,
        "hangs": [
            {
                "order": h.order,
                "weights": "+".join(h.weight_ids),
                "n_weights": len(h.weight_ids),
                "tension_n": round(h.tension_n, 3),
                "predicted_volts": round(h.predicted_volts, 3),
                "u_volts": round(h.u_predicted_volts, 3),
                "reason": h.reason,
            }
            for h in p.hangs
        ],
    }


class _Handler(BaseHTTPRequestHandler):
    """Serves the page on GET / and the planner on POST /plan; writes nothing to disk."""

    def _send(self, code: int, ctype: str, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        """Serve the single page."""
        if self.path in ("/", "/index.html"):
            self._send(200, "text/html; charset=utf-8", PAGE.encode("utf-8"))
        else:
            self._send(404, "text/plain", b"not found")

    def do_POST(self) -> None:  # noqa: N802 - http.server API
        """Run the planner on a JSON form body."""
        if self.path != "/plan":
            self._send(404, "text/plain", b"not found")
            return
        try:
            n = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            n = -1
        if not 0 <= n <= _MAX_BODY:
            self._send(413, "text/plain", b"bad body size")
            return
        try:
            form = json.loads(self.rfile.read(n) or b"{}")
            if not isinstance(form, dict):
                raise ValueError("body must be a JSON object")
        except ValueError as exc:
            _log.warning("bad /plan body: %s", exc)
            self._send(400, "application/json", json.dumps({"ok": False, "error": str(exc)}).encode())
            return
        self._send(200, "application/json", json.dumps(plan_from_form(form)).encode())

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        """Route http.server access logs through the module logger."""
        _log.debug("http %s", format % args)


def make_server(port: int = 0) -> HTTPServer:
    """Bind a loopback-only server; port 0 picks a free port."""
    srv = HTTPServer((HOST, port), _Handler)
    srv.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    return srv


def main(argv: list[str] | None = None) -> int:
    """Start the planner server, open the browser and serve until interrupted."""
    ap = argparse.ArgumentParser(description="Browser weight planner (advisory; saves nothing).")
    ap.add_argument("--port", type=int, default=0, help="port to bind on 127.0.0.1 (default: a free one)")
    ap.add_argument("--no-browser", action="store_true", help="only print the URL")
    args = ap.parse_args(argv)
    logging.getLogger("sadi").setLevel(logging.WARNING)
    srv = make_server(args.port)
    url = f"http://{HOST}:{srv.server_address[1]}/"
    _log.info("weight planner at %s", url)
    sys.stdout.write(f"Weight planner (advisory, saves nothing): {url}\nCtrl+C to stop.\n")
    sys.stdout.flush()
    if not args.no_browser:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        _log.info("shutting down")
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
