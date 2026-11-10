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

from sadi.design.cli import build_request
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
<label>Weights (kg, comma separated; repeat a value for duplicate weights, max 12)<br>
<textarea name="weights" required>0.02,0.05,0.05,0.1,0.1,0.2,0.01,0.03</textarea></label>
<label>Mass uncertainty per weight, kg <input type="text" name="u_mass" value="0.0001"></label>
</fieldset>
<fieldset><legend>Wire</legend>
<label>Diameter, m <input type="text" name="diameter" value="0.0002019" required></label>
<label>Diameter uncertainty, m <input type="text" name="u_diameter" value="0"></label>
<label>Gauge length L0, m <input type="text" name="length" value="0.08313" required></label>
<label>L0 uncertainty, m <input type="text" name="u_length" value="0"></label>
</fieldset>
<fieldset><legend>LVDT calibration</legend>
<label>Calibration slope, V per m (REQUIRED, from your own calibration; no default is assumed)
<input type="text" name="cal_slope" required placeholder="e.g. your measured V/m"></label>
<small>An earlier 40 V/m figure was only a placeholder and is NOT used here.</small>
<label>Calibration offset, V <input type="text" name="cal_offset" value="0"></label>
<label>Saturation limit, V (blank = built-in default) <input type="text" name="saturation" value=""></label>
</fieldset>
<fieldset><legend>Already captured</legend>
<label>Points as kg:volts, comma separated (blank = none)<br>
<textarea name="captured"></textarea></label>
</fieldset>
<button type="submit">Plan</button>
</form>
<div id="out"></div>
<script>
const out = document.getElementById("out");
function cell(t, cls){const td=document.createElement("td"); if(cls) td.className=cls; td.textContent=t; return td;}
document.getElementById("f").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const body = {};
  for (const [k, v] of new FormData(ev.target).entries()) body[k] = v;
  out.textContent = "Planning...";
  let data;
  try {
    const r = await fetch("/plan", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
    data = await r.json();
  } catch (e) { out.innerHTML = ""; const p = document.createElement("p"); p.className = "err"; p.textContent = "Request failed: " + e; out.appendChild(p); return; }
  out.innerHTML = "";
  if (!data.ok) { const p = document.createElement("p"); p.className = "err"; p.textContent = "No plan: " + data.error; out.appendChild(p); return; }
  const s = document.createElement("p");
  s.textContent = "Phase: " + data.phase + ". Inventory loads " + data.n_inventory + ", achievable " + data.n_achievable +
    ", usable " + data.n_usable + ". Dropped: " + data.dropped_saturation + " saturating, " + data.dropped_capacity + " over wire capacity. (Advisory; nothing saved.)";
  out.appendChild(s);
  const t = document.createElement("table");
  const hr = t.insertRow();
  for (const h of ["#", "Hang (weights)", "Total kg", "Tension N", "Predicted V", "+/- V", "Reason"]) { const th = document.createElement("th"); th.textContent = h; hr.appendChild(th); }
  for (const h of data.hangs) {
    const r = t.insertRow();
    r.appendChild(cell(h.order)); r.appendChild(cell(h.weights, "l")); r.appendChild(cell(h.total_kg));
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


def plan_from_form(form: dict[str, Any]) -> dict[str, Any]:
    """Turn a submitted form into the JSON reply: {'ok': True, ...plan} or {'ok': False, 'error': msg}."""
    nums: dict[str, float | None] = {}
    spec = {
        "u_mass": (False, 0.0), "diameter": (True, None), "u_diameter": (False, 0.0),
        "length": (True, None), "u_length": (False, 0.0), "cal_slope": (True, None),
        "cal_offset": (False, 0.0), "saturation": (False, None),
    }
    for key, (required, default) in spec.items():
        got = _num(form, key, required=required, default=default)
        if isinstance(got, Err):
            return {"ok": False, "error": got.error}
        nums[key] = got.value
    built = build_request(
        weights=str(form.get("weights", "")), u_mass=nums["u_mass"] or 0.0,
        diameter=nums["diameter"] or 0.0, u_diameter=nums["u_diameter"] or 0.0,
        length=nums["length"] or 0.0, u_length=nums["u_length"] or 0.0,
        cal_slope=nums["cal_slope"] or 0.0, cal_offset=nums["cal_offset"] or 0.0,
        saturation=nums["saturation"], captured=str(form.get("captured", "")),
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
                "total_kg": round(h.total_mass_kg, 4),
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
