"""Headless driver: replay a scenario through the wizard over HTTP and recover E, yield, slope."""

# frob:ticket 01M71SYG3H3X7GJT21TE6MY8YC
from __future__ import annotations

import math
from typing import Any, Protocol, cast

from pydantic import BaseModel, ConfigDict
from typani import Err, ErrorSet, Ok, Result

from sadi.labs.lctt.calibration import fit_calibration
from sadi.labs.lctt.modulus import CurvePoint, fit_modulus
from sadi.labs.lctt.yield_ import find_yield
from sadi.logging_setup import get_logger
from sadi.synthetic.scenario import LONG_L0_M, SHORT_L0_M, G, PlannedPoint, Scenario
from sadi.uncertainty import Measured

_log = get_logger(__name__)

__all__ = ["DriveError", "DriveReport", "HttpClient", "analyse", "drive_lab"]


class HttpClient(Protocol):
    """The slice of httpx / Starlette TestClient the driver needs."""

    def get(self, url: str) -> Any:  # noqa: D102
        ...

    def post(self, url: str, *, json: Any = None) -> Any:  # noqa: D102
        ...


class DriveError(ErrorSet):
    """Why a replay stopped; the HTTP detail is in the log."""

    Http = "The server refused a step of the replay; see the log for the request and reply"
    Analysis = "The recovered data could not be fitted; see the log"


class DriveReport(BaseModel):
    """What a replayed lab recovered, next to the truth it was generated from."""

    model_config = ConfigDict(frozen=True)

    session: str
    synthetic: bool
    e_pa: float
    yield_pa: float
    cal_slope_m_per_v: float
    clamp_passed: bool | None
    n_elastic: int
    n_plastic: int
    excluded: int
    truth: dict[str, Any]

    def rel_errors(self) -> dict[str, float]:
        """Relative error of E, yield and calibration slope against the recorded truth."""
        t = self.truth
        return {
            "e": abs(self.e_pa - t["e_pa"]) / t["e_pa"],
            "yield": abs(self.yield_pa - t["yield_pa"]) / t["yield_pa"],
            "cal_slope": abs(self.cal_slope_m_per_v - t["cal_slope_m_per_v"])
            / t["cal_slope_m_per_v"],
        }


class _Replay:
    """One replay: holds the client, the raw-seq counter and the first failure."""

    def __init__(self, client: HttpClient) -> None:
        """Bind to `client`; raw sequence numbers advance 100 per posted point."""
        self.c = client
        self.seq = 1

    def call(
        self, method: str, url: str, body: Any = None, ok: tuple[int, ...] = (200, 201, 204)
    ) -> Any:
        """Issue a request; Err on a status outside `ok` (logged), else the reply."""
        res = self.c.get(url) if method == "GET" else self.c.post(url, json=body)
        if res.status_code not in ok:
            _log.error("replay %s %s -> %d: %s", method, url, res.status_code, res.text[:300])
            return Err(DriveError.Http)
        return Ok(res)

    def point(self, phase: str, inputs: dict[str, Any], **extra: Any) -> Result[str, DriveError]:
        """Capture one point; Ok is its point id."""
        window = {"first_raw_seq": self.seq, "last_raw_seq": self.seq + 99}
        self.seq += 100
        got = self.call(
            "POST",
            "/api/session/points",
            {"phase": phase, "inputs": inputs, "window": window, **extra},
        )
        if isinstance(got, Err):
            return Err(got.danger_err)
        return Ok(str(cast("dict[str, Any]", got.danger_ok.json()).get("point_id", "")))

    def step(self, verb: str, step: str) -> Result[Any, DriveError]:
        """Complete or skip a wizard step."""
        return self.call("POST", f"/api/session/wizard/{verb}", {"step": step})


def _load(p: PlannedPoint) -> tuple[dict[str, Any], dict[str, Any]]:
    """Typed inputs and capture extras for one planned load point."""
    return (
        {
            "volts": p.volts,
            "mass_kg": p.nominal_kg,
            "u_volts": p.u_volts,
            "u_mass_kg": p.u_mass_kg,
            "volts_sd": p.volts_sd,
        },
        {"t_since_load_s": p.t_since_load_s, "drift_rate": p.drift_rate, "settled": True},
    )


def _run(
    r: _Replay, sc: Scenario, phase: str, pts: tuple[PlannedPoint, ...]
) -> Result[int, DriveError]:
    """Post the specimen and every load point of a run, excluding faulty ones; Ok(excluded)."""
    spec = {
        "diameter": sc.diameter_m,
        "u_diameter": sc.u_diameter_m,
        "hanger_kg": sc.hanger_kg,
        "u_hanger_kg": sc.u_hanger_kg,
    }
    got = r.point("specimen", spec)
    if isinstance(got, Err):
        return Err(got.danger_err)
    excluded = 0
    for p in pts:
        inputs, extra = _load(p)
        made = r.point(phase, inputs, **extra)
        if isinstance(made, Err):
            return Err(made.danger_err)
        if p.fault is not None:
            ex = r.call(
                "POST", f"/api/session/points/{made.danger_ok}/edit", {"op": "exclude", "args": {}}
            )
            if isinstance(ex, Err):
                return Err(ex.danger_err)
            excluded += 1
    done = r.step("complete", phase)
    return Err(done.danger_err) if isinstance(done, Err) else Ok(excluded)


def _curve(
    pts: list[dict[str, Any]], sc: Scenario, slope: float, tare: float, l0: float
) -> list[CurvePoint]:
    """Stress-strain curve points built from stored load points (the lab's own formulas)."""
    area = math.pi * sc.diameter_m**2 / 4.0
    out = []
    for i, p in enumerate(pts):
        x = p["inputs"]
        stress = (x["mass_kg"] + sc.hanger_kg) * G / area
        strain = slope * (x["volts"] - tare) / l0
        s = Measured.create(stress, 0.0, "Pa").danger_ok
        e = Measured.create(strain, 0.0, "dimensionless").danger_ok
        out.append(CurvePoint(index=i, stress=s, strain=e))
    return out


def analyse(
    points: list[dict[str, Any]], sc: Scenario
) -> Result[tuple[float, float, float], DriveError]:
    """Recover (E, yield, calibration slope) from stored point views (excluded ones ignored)."""
    live = [p for p in points if not p["excluded"]]
    cal = [p for p in live if p["phase"] == "calibration"]
    fit = fit_calibration([p["inputs"]["volts"] for p in cal], [p["inputs"]["height"] for p in cal])
    if isinstance(fit, Err):
        _log.error("analyse: calibration fit failed: %s", fit.danger_err.name)
        return Err(DriveError.Analysis)
    slope = fit.danger_ok.slope.value
    tare = [p for p in live if p["phase"] == "tare"][-1]["inputs"]["mean"]
    el = _curve([p for p in live if p["phase"] == "elastic"], sc, slope, tare, LONG_L0_M)
    pl = _curve([p for p in live if p["phase"] == "plastic"], sc, slope, tare, SHORT_L0_M)
    e_fit = fit_modulus(el, 0, len(el) - 1)
    top = max(c.stress.value for c in pl)
    k = next(i for i, c in enumerate(pl) if c.stress.value > 0.5 * top)
    e_pl = fit_modulus(pl, 0, k - 1)
    if isinstance(e_fit, Err) or isinstance(e_pl, Err):
        _log.error("analyse: modulus fit failed")
        return Err(DriveError.Analysis)
    yld = find_yield(pl, e_pl.danger_ok.modulus)
    if isinstance(yld, Err):
        _log.error("analyse: yield failed: %s", yld.danger_err.name)
        return Err(DriveError.Analysis)
    return Ok((e_fit.danger_ok.modulus.value, yld.danger_ok.yield_stress.value, slope))


def drive_lab(
    client: HttpClient, sc: Scenario, slug: str = "synthetic-lab"
) -> Result[DriveReport, DriveError]:
    """Run the whole wizard (setup to export) against a server and fit the stored points."""
    r = _Replay(client)
    steps: list[Result[Any, DriveError]] = []
    made = r.call("POST", "/api/sessions", {"lab": "lctt", "slug": slug})
    if isinstance(made, Err):
        return Err(made.danger_err)
    name = made.danger_ok.json()["name"]
    for cyc in sc.setup:
        steps.append(r.point("setup", cyc.model_dump()))
    clamp = r.call("GET", "/api/session/clamp-check")
    passed = clamp.danger_ok.json().get("passed") if isinstance(clamp, Ok) else None
    steps.append(r.step("complete", "setup"))
    for c in sc.calibration:
        steps.append(r.point("calibration", c.model_dump()))
    steps.append(r.step("complete", "calibrate"))
    steps.append(r.point("tare", sc.tare.model_dump()))
    steps.append(r.step("complete", "tare"))
    for s in steps:
        if isinstance(s, Err):
            return Err(s.danger_err)
    ex_e = _run(r, sc, "elastic", sc.elastic)
    ex_p = _run(r, sc, "plastic", sc.plastic)
    for e in (ex_e, ex_p):
        if isinstance(e, Err):
            return Err(e.danger_err)
    listed = r.call("GET", "/api/session/points")
    if isinstance(listed, Err):
        return Err(listed.danger_err)
    got = r.call("GET", "/api/results")
    if isinstance(got, Err):
        return Err(got.danger_err)
    fmts = r.call("GET", "/api/export")
    if isinstance(fmts, Err):
        return Err(fmts.danger_err)
    exported = 0
    for f in fmts.danger_ok.json():
        if not f.get("download"):
            continue
        dl = r.call("GET", f"/api/export/{f['id']}")
        if isinstance(dl, Err):
            return Err(dl.danger_err)
        exported += 1
    _log.info("replay exported %d download formats", exported)
    body = listed.danger_ok.json()
    rows = body["points"] if isinstance(body, dict) else body
    rec = analyse(rows, sc)
    if isinstance(rec, Err):
        return Err(rec.danger_err)
    e_pa, y_pa, slope = rec.danger_ok
    info = r.call("GET", "/api/session")
    prov = info.danger_ok.json().get("provenance", {}) if isinstance(info, Ok) else {}
    report = DriveReport(
        session=name,
        synthetic=bool(prov.get("synthetic", False)),
        e_pa=e_pa,
        yield_pa=y_pa,
        cal_slope_m_per_v=slope,
        clamp_passed=passed,
        n_elastic=len(sc.elastic),
        n_plastic=len(sc.plastic),
        excluded=ex_e.danger_ok + ex_p.danger_ok,
        truth=sc.truth.model_dump(),
    )
    _log.info("replay done: %s rel errors %s", name, report.rel_errors())
    return Ok(report)
