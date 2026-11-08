// frob:ticket 01M6WV6TFKP2396PW58G1WJD3B
// frob:accept COV001 because="vitest tests; TypeScript test discovery needs grimble, not installed here"
import { describe, expect, it } from "vitest";
import { applyMessage } from "./useTrace";
import { loadMarkTime, resultMarkTime } from "./markClock";
import { decodeFrame } from "../ws/frame";
import { encodeTrace } from "../ws/testframes";
import { parseMessage } from "../ws/messages";
import { TraceWindow } from "../plots/live/window";

describe("stream clock vs record fields", () => {
  it("load mark is now minus time_since_load; result mark is window_end verbatim", () => {
    expect(loadMarkTime(12, 1.5)).toBeCloseTo(10.5);
    expect(loadMarkTime(12, null)).toBe(12);
    expect(resultMarkTime(12, 9)).toBe(9);
    expect(resultMarkTime(12, null)).toBe(12);
  });

  it("marks land on the trace-frame clock (t0_s)", () => {
    const w = new TraceWindow(10, 0);
    const mn = Array.from({ length: 100 }, () => 0);
    const r = decodeFrame(encodeTrace(1, 20, 0.001, { 0: [mn, mn] }));
    if (!r.ok || r.value.type !== "trace") throw new Error("bad frame");
    w.push(r.value); // stream now ~= 20.1
    const lp = { v: null as number | null };
    const st = parseMessage('{"kind":"state","raw_seq":1,"status":{"state":"creeping","point_index":0,"time_since_load":0.05}}');
    const rs = parseMessage('{"kind":"result","raw_seq":1,"record":{"point_index":0,"settled":true,"forced_early":false,"window_end":20.05}}');
    if (!st.ok || !rs.ok) throw new Error("bad msg");
    applyMessage(w, st.value, lp);
    applyMessage(w, rs.value, lp);
    const marks = w.snapshot(10).marks;
    expect(marks[0]?.t).toBeCloseTo(w.now - 0.05);
    expect(marks[1]?.t).toBe(20.05);
    expect(marks.every((m) => m.t <= w.now && m.t >= 20)).toBe(true);
  });
});
