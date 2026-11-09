// frob:ticket 01M6XA21NS7YS90E6TD81HNB2N
// Live-plot frame-rate benchmark on the simulator stream. Opt-in: set SADI_E2E_BENCH=1 (see docs/e2e.md).
import { BUDGET_60_MS, intervals, meets60fps, summarize } from "../src/plots/live/framestats";
import { expect, test } from "./fixtures";
import { expectStep, openWizard, skipSetup } from "./helpers";

const SECONDS = Number(process.env.SADI_E2E_BENCH_SECONDS ?? "8");

test("live trace keeps animating at 60 fps on the sim stream", async ({ page }) => {
  test.skip(process.env.SADI_E2E_BENCH !== "1", "opt-in benchmark: set SADI_E2E_BENCH=1");
  const mounted = await openWizard(page);
  test.skip(!mounted, "wizard shell did not mount (is the backend up? see docs/e2e.md)");

  await skipSetup(page);
  await expectStep(page, "calibration");
  const canvas = page.getByTestId("live-canvas");
  await expect(canvas).toBeVisible();
  await page.waitForTimeout(2_000); // let the stream fill the window and the JIT warm up

  // Sample requestAnimationFrame timestamps and canvas content changes inside the page.
  const run = await page.evaluate(async (ms) => {
    const el = document.querySelector<HTMLCanvasElement>('[data-testid="live-canvas"]');
    if (!el) throw new Error("live canvas missing");
    const stamps: number[] = [];
    const frames = new Set<string>();
    let last = 0;
    await new Promise<void>((done) => {
      const t0 = performance.now();
      const tick = (t: number): void => {
        stamps.push(t);
        if (t - last > 500) { last = t; frames.add(el.toDataURL().slice(-256)); }
        if (t - t0 < ms) requestAnimationFrame(tick); else done();
      };
      requestAnimationFrame(tick);
    });
    return { stamps, distinct: frames.size };
  }, SECONDS * 1000);

  const stats = summarize(intervals(run.stamps));
  process.stdout.write(`live-fps ${JSON.stringify({ ...stats, distinctCanvasSamples: run.distinct, budgetMs: BUDGET_60_MS })}\n`);
  expect(run.distinct, "canvas content must change while streaming").toBeGreaterThan(1);
  // Headless chromium on a shared CI box: gate on the same criterion as the node harness (mean >= 58 fps, p95 <= 1.25 budgets).
  expect(meets60fps(stats), JSON.stringify(stats)).toBe(true);
});
