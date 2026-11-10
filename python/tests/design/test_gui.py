"""Tests for the standalone browser weight planner (docs/design/planner-gui.md)."""

# creates:python/tests/design/test_gui.py
# frob:ticket 01M72ZGDCC7C75SMXSJRH6VBAE

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

import pytest

from sadi.design.gui import HOST, PAGE, make_server, plan_from_form

FORM = {
    "weights": "0.02,0.05,0.05,0.1,0.1,0.2,0.01,0.03", "u_mass": "0.0001", "diameter": "0.0002019",
    "u_diameter": "0", "length": "0.08313", "u_length": "0", "cal_slope": "12", "cal_offset": "0",
    "saturation": "", "captured": "",
}


@pytest.fixture
def server():
    srv = make_server(0)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://{HOST}:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


def test_plan_from_form_orders_hangs():
    out = plan_from_form(FORM)
    assert out["ok"] and out["advisory"]
    assert out["hangs"] and [h["order"] for h in out["hangs"]] == list(range(1, len(out["hangs"]) + 1))
    assert {"weights", "total_kg", "tension_n", "predicted_volts", "u_volts", "reason"} <= set(out["hangs"][0])


@pytest.mark.parametrize("missing", ["cal_slope", "diameter", "length"])
def test_required_fields_never_defaulted(missing):
    out = plan_from_form({**FORM, missing: ""})
    assert not out["ok"] and missing in out["error"]


def test_bad_number_and_bad_weights_are_errors():
    assert not plan_from_form({**FORM, "cal_slope": "abc"})["ok"]
    assert not plan_from_form({**FORM, "cal_slope": "nan"})["ok"]
    assert not plan_from_form({**FORM, "weights": "0.1,zz"})["ok"]


def test_captured_points_accepted():
    assert plan_from_form({**FORM, "captured": "0.05:0.3"})["ok"]


def test_page_is_self_contained_and_advisory():
    assert "Advisory only" in PAGE and "REQUIRED" in PAGE and "40 V/m" in PAGE
    assert "http://" not in PAGE.replace("http://127", "") and "https://" not in PAGE
    assert 'name="cal_slope" required' in PAGE and 'name="cal_slope" required value' not in PAGE


def test_server_binds_loopback_only():
    srv = make_server(0)
    try:
        assert srv.server_address[0] == "127.0.0.1"
    finally:
        srv.server_close()


def test_http_get_and_post(server):
    with urllib.request.urlopen(server + "/") as r:
        assert r.status == 200 and b"Weight planner" in r.read()
    req = urllib.request.Request(server + "/plan", data=json.dumps(FORM).encode(), method="POST")
    with urllib.request.urlopen(req) as r:
        assert json.loads(r.read())["ok"] is True


def test_http_errors(server):
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(server + "/nope")
    assert e.value.code == 404
    bad = urllib.request.Request(server + "/plan", data=b"[1]", method="POST")
    with pytest.raises(urllib.error.HTTPError) as e2:
        urllib.request.urlopen(bad)
    assert e2.value.code == 400
