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
    "weights": "0.2,0.5,0.5,1,1,2,0.1,0.3", "u_mass": "0.001", "diameter": "0.0002019",
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
    assert {"weights", "n_weights", "tension_n", "predicted_volts", "u_volts", "reason"} <= set(out["hangs"][0])


@pytest.mark.parametrize("missing", ["diameter", "length"])
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
    assert "Advisory only" in PAGE and "Add row" in PAGE and "LVDT slope" in PAGE
    assert "http://" not in PAGE.replace("http://127", "") and "https://" not in PAGE
    assert 'name="cal_slope" required' not in PAGE


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


def test_per_weight_uncertainty_is_parsed():
    from sadi.design.cli import parse_weights

    ws = parse_weights("0.1:0.001,0.2", 0.0005).unwrap()
    assert [w.u_mass_kg for w in ws] == [0.001, 0.0005]
    assert not isinstance(parse_weights("0.1:x", 0.0), type(ws))


def test_heights_and_weights_give_both_plans():
    out = plan_from_form({**FORM, "heights": "0.001:0.00001,0.002:0.00001,0.004:0.00001,0.006:0.00001"})
    assert out["ok"] and out["hangs"]
    hp = out["heights_plan"]
    assert hp["ok"] and hp["height_steps"]
    assert out["cal"]["se_slope"] == hp["se_slope_v_per_m"]


def test_heights_only_still_gives_height_plan():
    out = plan_from_form({**FORM, "weights": "", "heights": "0.001:0.00001,0.002:0.00001,0.004:0.00001"})
    assert out["ok"] and out["height_steps"] and "hangs" not in out


def test_page_orders_heights_and_calibration_before_weights():
    assert PAGE.index("Height inventory") < PAGE.index("LVDT calibration") < PAGE.index("Weight inventory")


def test_page_uses_grams_and_millimetres():
    assert "Mass, g" in PAGE and "Height, mm" in PAGE and "Mass, kg" not in PAGE and "Height, m<" not in PAGE
    assert "G_TO_KG" in PAGE and "MM_TO_M" in PAGE


def test_page_script_has_no_raw_newline_in_regex():
    """A raw newline inside a JS regex literal breaks the whole page (Python str escapes)."""
    import re

    js = re.search(r"<script>(.*)</script>", PAGE, re.S).group(1)
    assert not re.search(r"/\[?\n", js.replace("//", ""))


def test_height_plan_needs_no_slope_and_has_default_uncertainty():
    out = plan_from_form({"heights": "0.001,0.002,0.004,0.006", "cal_slope": ""})
    assert out["ok"] and out["height_steps"] and out["slope_known"] is False
    assert out["rel_se_slope"] is not None and out["se_slope_v_per_m"] is None
    assert all(s["predicted_volts"] is None and s["u_height_m"] == 1e-4 for s in out["height_steps"])


def test_height_default_uncertainty_is_overridable():
    out = plan_from_form({"heights": "0.001,0.002,0.004", "u_height_default": "0.0005"})
    assert all(s["u_height_m"] == 0.0005 for s in out["height_steps"])
    assert "Default height uncertainty" in PAGE
