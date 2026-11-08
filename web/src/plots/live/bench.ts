// frob:ticket 01M6WV6TH775MHY7HHMND4Z97Z
// frob:accept COV001 because="vitest tests; TypeScript test discovery needs grimble, not installed here"
/** Opt-in in-browser frame-rate harness for the live trace; never run by default. */
import { getLogger } from "../../api/log";
import { decodeFrame } from "../../ws/frame";
import { encodeTrace } from "../../ws/testframes";
import { intervals, summarize, type FrameStats } from "./framestats";
import { TraceWindow } from "./window";

const log = getLogger("plots.live.bench");

/** Injectable clock and frame scheduler (real browser: performance.now and requestAnimationFrame). */
export interface BenchEnv {
  readonly now: () => number;
  readonly raf: (cb: (t: number) => void) => void;
}

/** Run `frames` animation frames, each pushing one 256-bucket trace frame and snapshotting `columns`. */
export function runFrameBench(env: BenchEnv, frames = 600, columns = 1200): Promise<FrameStats> {
  const win = new TraceWindow(10, 0);
  const stamps: number[] = [];
  let seq = 0;
  return new Promise((resolve) => {
    const tick = (): void => {
      stamps.push(env.now());
      const mn = Array.from({ length: 256 }, (_, i) => Math.sin((i + seq) / 10));
      const mx = mn.map((v) => v + 0.2);
      const r = decodeFrame(encodeTrace(seq, seq * 0.02, 0.02 / 256, { 0: [mn, mx] }));
      if (r.ok && r.value.type === "trace") win.push(r.value);
      win.snapshot(columns);
      seq++;
      if (seq < frames) { env.raf(tick); return; }
      const stats = summarize(intervals(stamps));
      log.info("bench done", { ...stats });
      resolve(stats);
    };
    env.raf(tick);
  });
}

/** Expose `window.__sadiLiveBench()` so a human can run the benchmark from the devtools console. */
export function installBench(): void {
  (globalThis as unknown as Record<string, unknown>)["__sadiLiveBench"] = () =>
    runFrameBench({ now: () => performance.now(), raf: (cb) => { requestAnimationFrame(cb); } });
}
