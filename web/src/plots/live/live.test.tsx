// frob:ticket 01M6W7RAH93KKNK1WH67KWS2S7
// frob:accept COV001 because="vitest tests; TypeScript test discovery needs grimble, not installed here"
import { describe, expect, it } from "vitest";
import { renderToString } from "react-dom/server";
import { sceneToSvg, validateScene } from "../core";
import { applyMessage } from "../../hooks/useTrace";
import { decodeFrame, type TraceFrame } from "../../ws/frame";
import { encodeTrace } from "../../ws/testframes";
import { LivePlot } from "./LivePlot";
import { buildLiveScene, connLine, liveYRange, MIN_LIVE_FONT } from "./scene";
import { squareSide } from "./useContainerSquare";
import { TraceWindow } from "./window";

function frame(seq: number, t0: number, n: number, amp = 1, dt = 0.001): TraceFrame {
  const mn = Array.from({ length: n }, (_, i) => Math.sin(i / 10) * amp - 0.1);
  const mx = mn.map((v) => v + 0.2);
  const r = decodeFrame(encodeTrace(seq, t0, dt, { 0: [mn, mx] }));
  if (!r.ok || r.value.type !== "trace") throw new Error("bad test frame");
  return r.value;
}

describe("TraceWindow", () => {
  it("scrolls: old buckets leave, envelope keeps extremes", () => {
    const w = new TraceWindow(1, 0);
    // 20 frames of 50 ms, 256 points each => 1 s of history after 20 frames, plus more
    for (let i = 0; i < 40; i++) w.push(frame(i, i * 0.05, 256));
    const s = w.snapshot(100);
    expect(s.t1 - s.t0).toBeCloseTo(1);
    expect(s.x[0] as number).toBeGreaterThanOrEqual(s.t0 - 0.02);
    expect(s.x.length).toBe(100);
    expect(Math.max(...s.hi)).toBeCloseTo(1.1, 1);
    expect(Math.min(...s.lo)).toBeCloseTo(-1.1, 1);
    expect(w.size).toBeLessThan(40 * 256);
  });
  it("counts dropped frames from seq gaps and tracks stale", () => {
    const w = new TraceWindow(5, 0);
    w.push(frame(1, 0, 4));
    w.push(frame(5, 0.1, 4));
    expect(w.snapshot(10).droppedFrames).toBe(3);
  });
  it("keeps marks until they scroll out", () => {
    const w = new TraceWindow(1, 0);
    w.push(frame(0, 0, 8));
    w.mark({ t: 0.001, kind: "load", label: "load 0" });
    expect(w.snapshot(10).marks).toHaveLength(1);
    for (let i = 1; i < 60; i++) w.push(frame(i, i * 0.05, 256));
    expect(w.snapshot(10).marks).toHaveLength(0);
  });
});

describe("applyMessage", () => {
  it("turns state and result messages into marks", () => {
    const w = new TraceWindow(10, 0);
    w.push(frame(0, 5, 256));
    const last: { v: number | null } = { v: null };
    applyMessage(w, { kind: "state", rawSeq: 1, state: "loading", pointIndex: 0, timeSinceLoad: 0.1 }, last);
    applyMessage(w, { kind: "state", rawSeq: 2, state: "creeping", pointIndex: 0, timeSinceLoad: 0.2 }, last);
    applyMessage(w, { kind: "result", rawSeq: 3, pointIndex: 0, settled: true, forcedEarly: false, windowEnd: 5.1 }, last);
    applyMessage(w, { kind: "result", rawSeq: 4, pointIndex: 1, settled: false, forcedEarly: true, windowEnd: null }, last);
    expect(w.snapshot(10).marks.map((m) => m.kind)).toEqual(["load", "settled", "forced"]);
    expect(applyMessage(w, { kind: "stopped", reason: "overload", hint: "reduce load" }, last)).toContain("range");
    const fault = applyMessage(w, { kind: "stopped", reason: "device_fault", hint: "x" }, { v: null });
    expect(fault).toContain("capture a point first");
    expect(fault).not.toContain("Stopped: device_fault");
  });
});

describe("live scene", () => {
  it("is titled with unit axes, legend, limits at +-4.9 V and renders (acceptance 1, 3)", () => {
    const w = new TraceWindow(10, 0);
    w.push(frame(0, 0, 256, 4.5));
    w.mark({ t: 0.1, kind: "load", label: "load 0" });
    const scene = buildLiveScene(w.snapshot(300), { conn: { status: "reconnecting", attempt: 2, delayMs: 500 } });
    expect(validateScene(scene).ok).toBe(true);
    expect(scene.fits?.map((f) => f.y[0])).toEqual([4.9, -4.9]);
    const svg = sceneToSvg(scene);
    expect(svg).toContain("Live trace");
    expect(svg).toContain("Time (s)");
    expect(svg).toContain("Voltage (V)");
    expect(svg).toContain("Reconnecting (attempt 2, retry in 0.5 s)");
    expect(svg).toContain("min/max envelope");
    expect(svg).toContain("load 0");
  });
  it("renders with no data and describes connection states", () => {
    const scene = buildLiveScene(new TraceWindow(10, 0).snapshot(10));
    expect(sceneToSvg(scene)).toContain("Live trace");
    expect(connLine({ status: "open" }, true)).toBe("Stale data");
    expect(connLine({ status: "open" }, false)).toBeNull();
    expect(connLine({ status: "closed" }, false)).toBe("Disconnected");
  });
  it("component renders server-side with a canvas and export hint", () => {
    const html = renderToString(<LivePlot open={() => ({ close: () => undefined })} />);
    expect(html).toContain("live-canvas");
    expect(html).toContain("F3");
  });
});

describe("benchmark: 50 kS/s", () => {
  it("decode + window + snapshot stays far under 16 ms per frame", () => {
    // 50 kS/s with 1000-sample blocks => 50 frames/s, each decimated to 256 buckets, 2 channels
    const n = 256;
    const mn = Array.from({ length: n }, (_, i) => Math.sin(i / 7));
    const mx = mn.map((v) => v + 0.05);
    const w = new TraceWindow(10, 0);
    const bufs: ArrayBuffer[] = [];
    for (let i = 0; i < 500; i++) bufs.push(encodeTrace(i, i * 0.02, 0.00002, { 0: [mn, mx], 1: [mn, mx] }));
    const times: number[] = [];
    for (const b of bufs) {
      const t = performance.now();
      const r = decodeFrame(b);
      if (r.ok && r.value.type === "trace") w.push(r.value);
      w.snapshot(600); // a render tick per frame is the worst case
      times.push(performance.now() - t);
    }
    times.sort((a, b) => a - b);
    const p95 = times[Math.floor(times.length * 0.95)] as number;
    expect(p95).toBeLessThan(8);
    expect(times.reduce((a, b) => a + b, 0) / times.length).toBeLessThan(4);
  });
});

// regression test for audit1#26 live trace auto-scales to the signal
describe("liveYRange", () => {
  it("auto-scales a millivolt signal and drops the saturation limits", () => {
    const w = new TraceWindow(1, 0);
    w.push(frame(1, 0, 64, 0.001));
    const snap = w.snapshot(50);
    const r = liveYRange(snap);
    expect(r.rails).toBe(false);
    expect(r.max - r.min).toBeLessThan(1);
    const sc = buildLiveScene(snap);
    expect(sc.yAxis.max).toBeLessThan(0.5);
    expect(sc.fits).toHaveLength(0);
    expect(sc.theme.fontSize.tick).toBeGreaterThanOrEqual(14);
  });
  it("keeps the rails view once the signal nears saturation", () => {
    const w = new TraceWindow(1, 0);
    w.push(frame(1, 0, 64, 4));
    const r = liveYRange(w.snapshot(50));
    expect(r.rails).toBe(true);
    expect(r.max).toBe(5.5);
    expect(buildLiveScene(w.snapshot(50)).fits).toHaveLength(2);
  });
});

// frob:ticket 01M72VM5X86QRPEWSW65Q9RBD8
describe("square live scene", () => {
  it("is square at the container side and keeps fonts >= 12 px", () => {
    const side = squareSide(350);
    const sc = buildLiveScene(new TraceWindow(1, 0).snapshot(10), { width: side, height: side });
    expect(sc.width).toBe(sc.height);
    expect(sc.width).toBe(350);
    expect(Math.min(...Object.values(sc.theme?.fontSize ?? {}))).toBeGreaterThanOrEqual(MIN_LIVE_FONT);
  });
  it("clamps tiny and unmeasured containers", () => {
    expect(squareSide(10)).toBe(240);
    expect(squareSide(0)).toBe(360);
  });
});
