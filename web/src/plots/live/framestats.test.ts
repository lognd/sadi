// frob:ticket 01M6WV6TH775MHY7HHMND4Z97Z
// frob:accept COV001 because="vitest tests; TypeScript test discovery needs grimble, not installed here"
import { describe, expect, it } from "vitest";
import { BUDGET_60_MS, intervals, meets60fps, percentile, summarize } from "./framestats";
import { runFrameBench } from "./bench";

describe("framestats", () => {
  it("computes intervals and percentiles", () => {
    expect(intervals([0, 10, 25])).toEqual([10, 15]);
    expect(percentile([5, 1, 3, 2, 4], 0.5)).toBe(3);
    expect(percentile([], 0.5)).toBeNaN();
  });
  it("accepts a steady 60 fps run and rejects a janky one", () => {
    const good = summarize(Array.from({ length: 100 }, () => BUDGET_60_MS));
    expect(good.fps).toBeCloseTo(60);
    expect(good.droppedFrames).toBe(0);
    expect(meets60fps(good)).toBe(true);
    const bad = summarize([...Array.from({ length: 90 }, () => 16), ...Array.from({ length: 10 }, () => 50)]);
    expect(bad.droppedFrames).toBeGreaterThan(0);
    expect(meets60fps(bad)).toBe(false);
    expect(meets60fps(summarize([]))).toBe(false);
  });
});

describe("runFrameBench harness", () => {
  it("drives the pipeline on a fake 60 Hz clock and reports the frame count", async () => {
    let t = 0;
    const stats = await runFrameBench({ now: () => t, raf: (cb) => { t += BUDGET_60_MS; queueMicrotask(() => { cb(t); }); } }, 30, 100);
    expect(stats.frames).toBe(29);
    expect(meets60fps(stats)).toBe(true);
  });
});
