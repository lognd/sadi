// frob:ticket 01M6W7RB9Q00GBJ5CJ0GW7ER11
// frob:ticket 01M6W7RB7ZFKF3DVKWW74FQXWT
// creates:web/e2e/run-capture.spec.ts
// Run-screen capture phases (covers ~A7JNFGT). Requires chromium and `sadi --sim`; see docs/e2e.md.
import { expect, test } from "@playwright/test";
import { acceptWhenSettled, expectStep, openWizard, skipSetup } from "./helpers";

test("simulator banner, live readout and Space capture on the calibrate screen", async ({ page }) => {
  const mounted = await openWizard(page);
  test.skip(!mounted, "wizard shell did not mount (is the backend up? see docs/e2e.md)");

  await skipSetup(page); // Setup needs captured points and has no capture UI; skip it
  await expectStep(page, "calibration");
  await expect(page.getByTestId("sim-banner")).toHaveText("SIMULATED DATA");
  await expect(page.getByTestId("readout")).toContainText("Live V:");
  await expect(page.getByTestId("live-canvas")).toBeVisible();
  await acceptWhenSettled(page);
});

test("each capture phase shows its heading and accepts a point", async ({ page }) => {
  const mounted = await openWizard(page);
  test.skip(!mounted, "wizard shell did not mount (is the backend up? see docs/e2e.md)");

  await skipSetup(page);
  for (const [phase, heading] of [["calibration", /Calibrate/], ["Tare", /Tare/], ["Elastic", /Elastic/], ["Plastic", /Plastic/]] as const) {
    await expectStep(page, phase);
    await expect(page.getByRole("heading", { name: heading })).toBeVisible();
    await acceptWhenSettled(page);
    await page.keyboard.press("Enter");
  }
});
