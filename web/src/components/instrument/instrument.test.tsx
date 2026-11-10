// frob:ticket 01M71SKWW36NDBJK24QD7DHSW4
// frob:accept COV001 because="test file; TypeScript test discovery needs grimble, not installed here"
import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { fakeLive } from "../../state/testLive";
import { calibFrom, displacementMm } from "./calibration";
import { DebugStripView, frameAge, unavailable } from "./DebugStrip";
import { InstrumentBarView, settleWord } from "./InstrumentBar";
import type { BackendFacts } from "./useBackendFacts";
import { plainNote } from "../wizard/plainText";
import { STEP_GUIDE } from "../wizard/stepGuide";

const EMPTY: BackendFacts = { save: null, device: null, session: null, rootLockOk: null, dataRoot: null, version: null, lastError: null };

describe("InstrumentBarView", () => {
  it("says not calibrated yet without calibration", () => {
    const l = fakeLive({ view: { volts: 1.25, source: "simulated" } });
    const html = renderToString(<InstrumentBarView view={l.view} conn={l.conn} calib={null} />);
    expect(html).toContain("not calibrated yet");
    expect(html).toContain("1.2500");
    expect(html).toContain("SIMULATED");
  });
  it("shows displacement when calibrated", () => {
    const l = fakeLive({ view: { volts: 2 } });
    const html = renderToString(<InstrumentBarView view={l.view} conn={l.conn} calib={{ slope: 0.001, tare: 1 }} />);
    expect(html).toContain("1.000 mm");
  });
  it("settleWord pairs glyph and word", () => {
    expect(settleWord(fakeLive({ view: { motion: "settled" } }).view)).toContain("Settled");
  });
});

describe("calibration", () => {
  it("needs both slope and tare", () => {
    const rs = { values: [{ name: "slope", value: 2 }] } as unknown as Parameters<typeof calibFrom>[0];
    expect(calibFrom(rs)).toBeNull();
    expect(displacementMm({ slope: 0.002, tare: 0 }, 1)).toBeCloseTo(2);
  });
});

describe("DebugStripView", () => {
  it("shows unavailable fields with a reason and the frame age", () => {
    const html = renderToString(<DebugStripView meta={{ seq: 5, durableSeq: 4, enqueuedSeq: 5, dtS: 0.01, atMs: 100 }} nowMs={150} facts={EMPTY} backend="[ok] up" />);
    expect(html).toContain("unavailable (");
    expect(html).toContain("50 ms");
    expect(html).toContain("5");
  });
  it("frameAge flags stale frames", () => {
    expect(frameAge(null, 0).state).toBe("none");
    expect(frameAge({ seq: 1, durableSeq: 0, enqueuedSeq: 1, dtS: 0, atMs: 0 }, 5000).state).toBe("stale");
    expect(unavailable("x")).toBe("unavailable (x)");
  });
});

describe("plainNote", () => {
  it("rewrites TOO_FEW_POINTS", () => {
    expect(plainNote("ComputeCode.TOO_FEW_POINTS")).toContain("capture at least 3 points");
  });
  it("step guide has short do-this lists", () => {
    for (const g of Object.values(STEP_GUIDE)) expect(g.doThis.length).toBeLessThanOrEqual(4);
  });
});
