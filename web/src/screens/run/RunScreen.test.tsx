// frob:ticket 01M6W7RB7ZFKF3DVKWW74FQXWT
// frob:ticket 01M71RCHHEM9EKV4SAEYTVC4WD
// frob:accept COV001 because="vitest tests; TypeScript test discovery needs grimble, not installed here"
import { renderToString as rts } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { applyMessage } from "../../hooks/useTrace";
import { TraceWindow } from "../../plots/live";
import type { ConnState } from "../../ws/client";
import { decodeFrame } from "../../ws/frame";
import { parseMessage, type ServerMessage } from "../../ws/messages";
import { encodeTrace } from "../../ws/testframes";
import { buildBody, decide, newRequestId, postCapture } from "./capture";
import { postLoadChange } from "./loadChange";
import { PHASES } from "./phases";
import { countPhasePoints, finishBlockedWhy } from "./pointCount";
import type { PointView } from "../review/types";
import { deriveLive, driftOver, signalOf, type LiveView } from "./live";
import { RunPlot, RunView, settleText, type RunViewProps } from "./RunView";
import { guidanceText, GENERIC_GUIDANCE } from "./guidance";
import { exportErrorText, fetchRunExport } from "./exportTrace";
import { foldSide, type SideState } from "./useRunLive";

const html = (el: React.JSX.Element): string => rts(el).replaceAll("<!-- -->", "");
const OPEN: ConnState = { status: "open" };

/** Mocked sim-like stream: a trace frame per 50 ms around `level` volts, plus JSON side-channel texts. */
function simStream(levels: number[], texts: string[]): { w: TraceWindow; side: SideState } {
  const w = new TraceWindow(5, 0);
  const lastPoint: { v: number | null } = { v: null };
  let side: SideState = { settle: null, rawSeq: 0, pointIndex: null, driftVps: null, window: null, simulated: false };
  levels.forEach((lv, i) => {
    const n = 64;
    const mn = Array.from({ length: n }, () => lv - 0.001);
    const mx = mn.map((v) => v + 0.002);
    const f = decodeFrame(encodeTrace(i, i * 0.05, 0.05 / n, { 0: [mn, mx] }));
    if (f.ok && f.value.type === "trace") w.push(f.value);
  });
  for (const t of texts) {
    const m = parseMessage(t);
    if (m.ok) { applyMessage(w, m.value, lastPoint); side = foldSide(side, m.value); }
  }
  return { w, side };
}
const state = (st: string, seq = 7): string => JSON.stringify({ kind: "state", raw_seq: seq, status: { state: st, point_index: 1, time_since_load: 3 } });
const flat = (n: number, v: number): number[] => Array.from({ length: n }, () => v);

const view = (o: Partial<LiveView> = {}): LiveView =>
  ({ volts: 1.2345, driftVps: 0, signal: "ok", motion: "settled", source: "simulated", stale: false, ...o });
const props = (o: Partial<RunViewProps> = {}): RunViewProps => ({
  phase: "calibrate", view: view(), blockedWhy: null,
  confirming: false, message: null, fields: {}, onField: () => undefined, onAccept: () => undefined, onLoadChange: () => undefined, onConfirmEarly: () => undefined, onCancelEarly: () => undefined, ...o,
});

describe("live derivation from a mocked sim stream", () => {
  it("settled stream: readout, motion and signal", () => {
    const { w, side } = simStream(flat(40, 1.2345), [state("settled")]);
    const v = deriveLive(w.snapshot(100), OPEN, side.settle, true);
    expect(v.volts).toBeCloseTo(1.2345, 3);
    expect(v.motion).toBe("settled");
    expect(v.signal).toBe("ok");
    expect(v.source).toBe("simulated");
    expect(side.rawSeq).toBe(7);
  });
  it("creeping stream reports a drift rate", () => {
    const { w, side } = simStream(Array.from({ length: 40 }, (_, i) => 1 + i * 0.002), [state("creeping")]);
    const v = deriveLive(w.snapshot(100), OPEN, side.settle, true);
    expect(v.motion).toBe("creeping");
    expect(v.driftVps).toBeCloseTo(0.04, 2);
    expect(settleText(v)).toMatch(/^\[Creeping (39|40)\.\d mV\/s\]$/);
  });
  it("saturation shows in the status bar signal and the warning", () => {
    const { w } = simStream(flat(40, 4.95), [state("settled")]);
    const v = deriveLive(w.snapshot(100), OPEN, "settled", false);
    expect(v.signal).toBe("saturated");
    expect(signalOf(simStream(flat(40, 4.5), []).w.snapshot(100))).toBe("near-limit");
    expect(html(<RunView {...props({ view: v })} />)).toContain("saturated");
  });
  it("disconnect marks Disconnected, stale and pauses capture", () => {
    const { w } = simStream(flat(10, 1), []);
    const v = deriveLive(w.snapshot(50), { status: "reconnecting", attempt: 2, delayMs: 500 }, "settled", false);
    expect(v.source).toBe("disconnected");
    expect(v.stale).toBe(true);
    const d = decide(v, false, "idle");
    expect(d.kind).toBe("blocked");
    const out = html(<RunView {...props({ view: v, blockedWhy: d.kind === "blocked" ? d.why : null })} />);
    expect(out).toContain("disconnect-notice");
    expect(out).toContain("disabled");
  });
  it("driftOver needs three columns", () => {
    expect(driftOver(new Float64Array([0, 1]), new Float64Array([0, 1]), 0)).toBeNull();
  });
  it("foldSide keeps server drift, capture window and simulated flag; deriveLive prefers server drift", () => {
    const m = parseMessage('{"kind":"state","raw_seq":9,"drift_vps":0.25,"simulated":true,"window":{"first_raw_seq":4,"last_raw_seq":9},"status":{"state":"creeping","point_index":2}}');
    const s0: SideState = { settle: null, rawSeq: 0, pointIndex: null, driftVps: null, window: null, simulated: false };
    const s = m.ok ? foldSide(s0, m.value) : s0;
    expect(s).toMatchObject({ driftVps: 0.25, window: { firstRawSeq: 4, lastRawSeq: 9 }, simulated: true });
    const w = new TraceWindow(5, 0);
    expect(deriveLive(w.snapshot(100), OPEN, s.settle, s.simulated, s.driftVps).driftVps).toBe(0.25);
  });
  it("foldSide keeps simulated sticky after a state message omits it (fault)", () => {
    const s: SideState = { settle: null, rawSeq: 1, pointIndex: null, driftVps: null, window: null, simulated: true };
    const st = parseMessage('{"kind":"state","raw_seq":2,"simulated":false,"status":{"state":"settled"}}');
    expect((st.ok ? foldSide(s, st.value) : s).simulated).toBe(true);
  });
  it("foldSide keeps the newest guidance and state messages preserve it", () => {
    const s: SideState = { settle: null, rawSeq: 1, pointIndex: null, driftVps: null, window: null, simulated: false };
    const g = parseMessage('{"kind":"guidance","phase":"elastic","next_action":"Add load","stop_early":true,"stop_reason":"met"}');
    const s1 = g.ok ? foldSide(s, g.value) : s;
    expect(s1.guidance).toEqual({ phase: "elastic", nextAction: "Add load", stopEarly: true, stopReason: "met" });
    const st = parseMessage('{"kind":"state","raw_seq":2,"status":{"state":"settled"}}');
    expect((st.ok ? foldSide(s1, st.value) : s1).guidance).toEqual(s1.guidance);
  });
  it("foldSide ignores unrelated kinds", () => {
    const s: SideState = { settle: null, rawSeq: 1, pointIndex: null, driftVps: null, window: null, simulated: false };
    const m: ServerMessage = { kind: "stats", sentFrames: 1, droppedFrames: 0 };
    expect(foldSide(s, m)).toBe(s);
  });
});

describe("capture decisions", () => {
  it("settled accepts, creeping blocks, early asks then captures", () => {
    expect(decide(view(), false, "idle").kind).toBe("capture");
    const creeping = view({ motion: "creeping" });
    expect(decide(creeping, false, "idle").kind).toBe("blocked");
    expect(decide(creeping, true, "idle").kind).toBe("confirm-early");
    expect(decide(creeping, true, "asking").kind).toBe("capture-early");
  });
  it("saturation blocks even a forced capture", () => {
    expect(decide(view({ signal: "saturated", motion: "creeping" }), true, "asking").kind).toBe("blocked");
    expect(decide(view({ volts: null }), false, "idle").kind).toBe("blocked");
  });
  it("body marks forced-early captures as unsettled", () => {
    const b = buildBody("elastic", { mass_kg: 0.2 }, 9, view({ motion: "creeping", driftVps: 0.01 }), true);
    expect(b).toMatchObject({ phase: "elastic", settled: false, forced_early: true, drift_rate: 0.01 });
    expect(buildBody("tare", {}, 9, view(), false)).toMatchObject({ phase: "tare", settled: true, forced_early: false });
  });
  // frob:ticket 01M72D37RN0VN65DDCSPWHJMJ7
  it("body carries the request_id only when given, and ids are unique", () => {
    expect(buildBody("tare", {}, 9, view(), false, "abc")).toMatchObject({ request_id: "abc" });
    expect(buildBody("tare", {}, 9, view(), false)).not.toHaveProperty("request_id");
    expect(newRequestId()).not.toBe(newRequestId());
  });
  it("postCapture posts JSON and surfaces refusals", async () => {
    const calls: string[] = [];
    const ok: typeof fetch = (i, init) => { calls.push(`${init?.method ?? "GET"} ${typeof i === "string" ? i : i instanceof URL ? i.href : i.url}`); return Promise.resolve(new Response(JSON.stringify({ seq: 3, summary: "p1" }), { status: 201 })); };
    const r = await postCapture(buildBody("calibrate", {}, 1, view(), false), ok);
    expect(r.ok).toBe(true);
    expect(calls).toEqual(["POST /api/session/points"]);
    const bad: typeof fetch = () => Promise.resolve(new Response("nope", { status: 409 }));
    const r2 = await postCapture(buildBody("calibrate", {}, 1, view(), false), bad);
    expect(r2.ok).toBe(false);
  });
});

describe("RunView", () => {
  it("shows accept button and phase wording; readout and trace live in the front panel", () => {
    const out = html(<RunView {...props()} />);
    expect(out).not.toContain("Live V:");
    expect(out).not.toContain("live-canvas");
    expect(out).toContain("Accept point (Space)");
    expect(out).not.toContain("saturation-warning");
  });
  it("forced-early confirmation replaces the accept button", () => {
    const out = html(<RunView {...props({ confirming: true, view: view({ motion: "creeping" }) })} />);
    expect(out).toContain("confirm-early");
    expect(out).toContain("recorded as unsettled");
  });
  it("per-phase plot: stress-strain for elastic, none for tare", () => {
    const data = { points: [], fit: null, yield: null };
    expect(html(<RunPlot plot={{ kind: "stress-strain", data }} />)).toContain("Stress-strain");
    expect(html(<RunPlot plot={null} />)).toBe("");
    expect(html(<RunView {...props({ phase: "tare" })} />)).toContain("Accept point (Space)");
  });
});

describe("run F3 export", () => {
  it("fetches the lctt-csv export", async () => {
    const urls: string[] = [];
    const f = ((u: string) => { urls.push(u); return Promise.resolve(new Response("a,b\n1,2\n")); }) as unknown as typeof fetch;
    const r = await fetchRunExport("lctt-csv", f);
    expect(urls).toEqual(["/api/export/lctt-csv"]);
    expect(r.ok && r.value.filename).toBe("sadi-lctt-csv.csv");
  });
  it("reports http and network failures", async () => {
    const bad = (() => Promise.resolve(new Response("nope", { status: 404 }))) as unknown as typeof fetch;
    const r = await fetchRunExport("x", bad);
    expect(!r.ok && exportErrorText(r.error)).toContain("HTTP 404");
    const down = (() => Promise.reject(new Error("down"))) as unknown as typeof fetch;
    const r2 = await fetchRunExport("x", down);
    expect(!r2.ok && exportErrorText(r2.error)).toContain("down");
  });
});

describe("mark load change", () => {
  it("RunView renders the Mark load change button", () => {
    expect(html(<RunView {...props()} />)).toContain("I moved to a new gauge block");
    expect(html(<RunView {...props()} />)).toContain("click it again after every Accept");
    expect(html(<RunView {...props({ phase: "elastic" })} />)).toContain("I added a weight");
    expect(html(<RunView {...props()} />)).not.toContain("Mark load change");
  });
  it("postLoadChange posts to the route and returns the marker seq", async () => {
    const calls: string[] = [];
    const f = ((url: string, init?: RequestInit) => {
      calls.push(`${init?.method ?? "GET"} ${url}`);
      return Promise.resolve(new Response(JSON.stringify({ marker_seq: 5 }), { status: 200 }));
    }) as typeof fetch;
    const r = await postLoadChange(f);
    expect(calls).toEqual(["POST /api/session/load-change"]);
    expect(r.ok && r.value.marker_seq).toBe(5);
  });
  it("postLoadChange surfaces a 409 as an error", async () => {
    const f = (() => Promise.resolve(new Response("{}", { status: 409 }))) as typeof fetch;
    const r = await postLoadChange(f);
    expect(r.ok).toBe(false);
  });
});

// frob:ticket 01M6XAASFHD7MKMQ79XRD34EXF
describe("RunView hotkey hint (U-04)", () => {
  it("is rendered and linked to the input fieldset", () => {
    const out = html(<RunView {...props()} />);
    expect(out).toContain('data-testid="hotkey-hint"');
    expect(out).toContain('aria-describedby="hotkey-hint"');
  });
});

// regression test for audit1#17 idle readout, audit1#31 guidance text, audit1#6 diameter warning
describe("audit1 run-screen fixes", () => {
  it("old frames make the readout idle: no stale volts, drift or saturation", () => {
    const { w } = simStream(flat(40, 4.99), [state("creeping")]);
    const v = deriveLive(w.snapshot(100), OPEN, "creeping", false, Number.NaN, 5000);
    expect(v.idle).toBe(true);
    expect(v.volts).toBeNull();
    expect(v.driftVps).toBeNull();
    expect(v.signal).toBe("ok");
    expect(v.motion).toBe("unknown");
    expect(decide(v, false, "idle").kind).toBe("blocked");
  });
  it("fresh frames are not idle and NaN drift becomes null", () => {
    const { w } = simStream(flat(40, 1), [state("settled")]);
    const v = deriveLive(w.snapshot(100), OPEN, "settled", false, Number.NaN, 100);
    expect(v.idle).toBeFalsy();
    expect(v.driftVps).toBeNull();
  });
  it("guidanceText replaces a zero-kg hang instruction", () => {
    expect(guidanceText("Add 0.000 kg of masses to the hanger (the hanger is added for you)")).not.toMatch(/0\.000/);
    // frob:ticket 01M72TEVXXFP3PZ84SABZEDX7H
    // single source: any load in guidance is dropped so it cannot disagree with SuggestedWeightPanel
    expect(guidanceText("Add 0.250 kg of masses to the hanger (the hanger is added for you)")).toBe(GENERIC_GUIDANCE);
    expect(guidanceText("Add 0.625 kg of masses")).not.toMatch(/0\.625/);
    expect(guidanceText("Wait for Settled")).toBe("Wait for Settled");
  });
  it("RunView warns on an implausible diameter and offers metres", () => {
    const out = html(<RunView {...props({ phase: "tare", fields: { diameter: "0.2" } })} />);
    expect(out).toContain('data-testid="plausible-diameter"');
  });
});

// frob:ticket 01M7274EKWS410XEGZGFD6HWHK
describe("capture card vocabulary and Finish gate", () => {
  it("every phase names its action Accept point and its mark button for the phase", () => {
    for (const ph of ["calibrate", "tare", "elastic", "plastic"] as const) {
      const out = html(<RunView {...props({ phase: ph })} />);
      expect(out).toContain("Accept point (Space)");
      expect(out).toContain(PHASES[ph].markLabel);
      expect(PHASES[ph].instruction).toContain(PHASES[ph].markLabel.length > 0 ? "Accept point" : "");
    }
  });
  it("shows the accepted point count against the minimum", () => {
    expect(html(<RunView {...props({ pointCount: 1 })} />)).toContain("Accepted points: 1 (at least 3 needed");
  });
  it("counts only non-excluded points of the phase", () => {
    const pt = (phase: string, excluded: boolean): PointView => ({ point_id: "x", seq: 1, phase, excluded, inputs: {}, window: {} as PointView["window"], history: [] });
    expect(countPhasePoints([pt("calibration", false), pt("calibration", true), pt("tare", false)], "calibrate")).toBe(1);
  });
  it("Finish is blocked below the minimum and open at or above it or while unknown", () => {
    expect(finishBlockedWhy("calibrate", 1)).toContain("at least 3 points");
    expect(finishBlockedWhy("calibrate", 3)).toBeNull();
    expect(finishBlockedWhy("calibrate", null)).toBeNull();
  });
});
