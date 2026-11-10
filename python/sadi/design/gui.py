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
<fieldset><legend>Weights</legend>
<label>Weights (newtons, N, comma separated; repeat a value for duplicate weights, max 12)<br>
<textarea name="weights" required>0.2,0.5,0.5,1,1,2,0.1,0.3</textarea></label>
<label>Force uncertainty per weight, N <input type="text" name="u_mass" value="0.001"></label>
<label>Number of hangs <input type="text" name="hangs" value="5"></label>
</fieldset>
<fieldset><legend>Wire</legend>
<label>Diameter, m <input type="text" name="diameter" value="0.0002019" required></label>
<label>Diameter uncertainty, m <input type="text" name="u_diameter" value="0"></label>
<label>Gauge length L0, m <input type="text" name="length" value="0.08313" required></label>
<label>L0 uncertainty, m <input type="text" name="u_length" value="0"></label>
</fieldset>
<fieldset><legend>LVDT calibration (fitted from your height / volts points)</legend>
<table id="cal"><thead><tr><th>Height, m</th><th>Volts, V</th></tr></thead><tbody></tbody></table>
<button type="button" id="addrow">Add row</button>
<small>Enter at least 3 points at 2 or more distinct heights; slope, intercept and their uncertainty are fitted. No default is assumed.</small>
<details><summary>Override (advanced)</summary>
<label>OVERRIDE slope, V per m (skips the fit; no uncertainty)
<input type="text" name="cal_slope" value="" placeholder="blank = use the fit"></label>
<label>OVERRIDE offset, V (with override only) <input type="text" name="cal_offset" value="0"></label>
</details>
<label>Saturation limit, V (blank = built-in default) <input type="text" name="saturation" value=""></label>
</fieldset>
<fieldset><legend>Gauge height inventory (which heights to calibrate with)</legend>
<table id="hts"><thead><tr><th>Height, m</th><th>Uncertainty, m</th></tr></thead><tbody></tbody></table>
<button type="button" id="addheight">Add row</button>
<small>Optional. Needs the override slope above as the nominal V per m; duplicates stay distinct. Fill it to get a height plan instead of a weight plan.</small>
</fieldset>
<fieldset><legend>Already captured</legend>
<label>Points as N:volts, comma separated (blank = none)<br>
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
const htsBody = document.querySelector("#hts tbody");
function addHeight(h, u){
  const tr = htsBody.insertRow();
  for (const val of [h, u]) { const td = tr.insertCell(); const i = document.createElement("input"); i.type = "text"; i.value = val; td.appendChild(i); }
}
for (let k = 0; k < 4; k++) addHeight("", "");
document.getElementById("addheight").addEventListener("click", () => addHeight("", ""));
function cell(t, cls){const td=document.createElement("td"); if(cls) td.className=cls; td.textContent=t; return td;}
document.getElementById("f").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const body = {};
  for (const [k, v] of new FormData(ev.target).entries()) body[k] = v;
  const pts = [];
  for (const tr of calBody.rows) { const [h, v] = [...tr.querySelectorAll("input")].map(i => i.value.trim()); if (h || v) pts.push(h + ":" + v); }
  body.cal_points = pts.join(",");
  const hts = [];
  for (const tr of htsBody.rows) { const [h, u] = [...tr.querySelectorAll("input")].map(i => i.value.trim()); if (h) hts.push(u ? h + ":" + u : h); }
  body.heights = hts.join(",");
  out.textContent = "Planning...";
  let data;
  try {
    const r = await fetch("/plan", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
    data = await r.json();
  } catch (e) { out.innerHTML = ""; const p = document.createElement("p"); p.className = "err"; p.textContent = "Request failed: " + e; out.appendChild(p); return; }
  out.innerHTML = "";
  if (!data.ok) { const p = document.createElement("p"); p.className = "err"; p.textContent = "No plan: " + data.error; out.appendChild(p); return; }
  if (data.height_steps) {
    const c0 = document.createElement("p");
    c0.textContent = "Heights to use (design estimate): slope se " + data.se_slope_v_per_m + " V/m, intercept se " + data.se_offset_v + " V.";
    out.appendChild(c0);
    const t0 = document.createElement("table");
    const hr0 = t0.insertRow();
    for (const h of ["#", "Id", "Height m", "u m", "Predicted V", "Slope se", "Offset se"]) { const th = document.createElement("th"); th.textContent = h; hr0.appendChild(th); }
    for (const h of data.height_steps) {
      const r = t0.insertRow();
      for (const v of [h.order, h.height_id, h.height_m, h.u_height_m, h.predicted_volts, h.se_slope_v_per_m, h.se_offset_v]) r.appendChild(cell(v === null ? "-" : v));
    }
    out.appendChild(t0);
    return;
  }
  const s = document.createElement("p");
  s.textContent = "Phase: " + data.phase + ". Inventory loads " + data.n_inventory + ", achievable " + data.n_achievable +
    ", usable " + data.n_usable + ". Dropped: " + data.dropped_saturation + " saturating, " + data.dropped_capacity + " over wire capacity. (Advisory; nothing saved.)";
  out.appendChild(s);
  const c = document.createElement("p"); c.textContent = data.calibration; out.appendChild(c);
  const t = document.createElement("table");
  const hr = t.insertRow();
  for (const h of ["#", "Hang (which weights)", "How many", "Total N", "Predicted V", "+/- V", "Reason"]) { const th = document.createElement("th"); th.textContent = h; hr.appendChild(th); }
  for (const h of data.hangs) {
    const r = t.insertRow();
    r.appendChild(cell(h.order)); r.appendChild(cell(h.weights, "l")); r.appendChild(cell(h.n_weights));
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
    """Turn a submitted form into the JSON reply: {'ok': True, ...plan} or {'ok': False, 'error': msg}."""
    if str(form.get("heights", "")).strip():
        return _heights_reply(form)
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
    built = build_request(
        weights=str(form.get("weights", "")), u_mass=nums["u_mass"] or 0.0,
        diameter=nums["diameter"] or 0.0, u_diameter=nums["u_diameter"] or 0.0,
        length=nums["length"] or 0.0, u_length=nums["u_length"] or 0.0,
        cal=cal.value,
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
        "calibration": cal.value.summary(),
        "cal": cal.value.model_dump(),
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
