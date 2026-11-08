// frob:ticket 01M6W7RB9Q00GBJ5CJ0GW7ER11
// creates:web/e2e/guided-run.spec.ts
// Requires a browser (chromium) and `sadi --sim` (sadi_py built); see docs/e2e.md.
import { readFile } from "node:fs/promises";
import { expect, test } from "@playwright/test";
import { acceptWhenSettled, currentStep, openWizard } from "./helpers";

test("keyboard-only guided run Setup -> Export against the simulator", async ({ page }) => {
  const mounted = await openWizard(page);
  test.skip(!mounted, "wizard shell did not mount (is the backend up? see docs/e2e.md)");

  expect(await currentStep(page)).toContain("Setup");
  await page.keyboard.press("Enter"); // Setup (or skip) -> Calibrate
  for (const phase of ["LVDT calibration", "Tare", "Elastic", "Plastic"]) {
    expect(await currentStep(page)).toContain(phase);
    const points = phase === "LVDT calibration" ? 3 : phase === "Plastic" ? 3 : 1;
    for (let i = 0; i < points; i += 1) await acceptWhenSettled(page);
    await page.keyboard.press("f"); // finish the phase
  }
  expect(await currentStep(page)).toContain("Results");
  await page.keyboard.press("Enter");

  expect(await currentStep(page)).toContain("Export");
  await expect(page.getByRole("region", { name: /results/i })).toContainText(/E\b/);

  const csv = page.waitForEvent("download");
  await page.keyboard.press("F3");
  const csvFile = await csv;
  const csvPath = await csvFile.path();
  expect((await readFile(csvPath)).length).toBeGreaterThan(0);
  expect(csvFile.suggestedFilename()).toMatch(/\.csv$/);

  const png = page.waitForEvent("download");
  await page.getByRole("button", { name: /figure|png/i }).focus();
  await page.keyboard.press("Enter");
  const pngFile = await png;
  const pngPath = await pngFile.path();
  const bytes = await readFile(pngPath);
  expect(bytes.length).toBeGreaterThan(0);
  expect(bytes.subarray(1, 4).toString("ascii")).toBe("PNG");
});
