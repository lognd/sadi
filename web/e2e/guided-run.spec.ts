// frob:ticket 01M6W7RB9Q00GBJ5CJ0GW7ER11
// creates:web/e2e/guided-run.spec.ts
// Requires a browser (chromium) and `sadi --sim` (sadi_py built); see docs/e2e.md.
import { expect, test } from "./fixtures";
import { acceptWhenSettled, expectStep, inputsFor, openWizard, skipSetup } from "./helpers";

test("keyboard-only guided run Setup -> Export against the simulator", async ({ page }) => {
  const mounted = await openWizard(page);
  test.skip(!mounted, "wizard shell did not mount (is the backend up? see docs/e2e.md)");

  await expectStep(page, "Setup");
  await skipSetup(page); // Setup needs captured points and has no capture UI; skip it
  for (const phase of ["LVDT calibration", "Tare", "Elastic", "Plastic"]) {
    await expectStep(page, phase);
    const points = phase === "LVDT calibration" ? 3 : phase === "Plastic" ? 3 : 1;
    for (let i = 0; i < points; i += 1) await acceptWhenSettled(page, inputsFor(phase, i));
    await page.keyboard.press("f"); // finish the phase
  }
  await expectStep(page, "Results");
  await page.keyboard.press("Enter");

  await expectStep(page, "Export");
  await expect(page.getByRole("region", { name: /results/i })).toContainText(/secant_modulus/);

  // frob:ticket 01M6X572N6WB1053QZ1WV4W4WY
  // The tare step also records the specimen geometry, so the LCTT CSV export is ready.
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: /download/i }).first().click();
  expect((await download).suggestedFilename()).toMatch(/\.csv$/i);
  // frob:ticket 01M6X7JNY6ZKZKDFRM3935NES4
  // Figure export fetches the figure data, renders it and saves a PNG download.
  const figure = page.waitForEvent("download");
  await page.getByRole("button", { name: /as png/i }).first().click();
  expect((await figure).suggestedFilename()).toMatch(/\.png$/i);
});
