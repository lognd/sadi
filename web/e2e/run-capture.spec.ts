// frob:ticket 01M6W7RB9Q00GBJ5CJ0GW7ER11
// frob:ticket 01M6W7RB7ZFKF3DVKWW74FQXWT
// creates:web/e2e/run-capture.spec.ts
// Run-screen capture phases (covers ~A7JNFGT). Requires chromium and `sadi --sim`; see docs/e2e.md.
import { expect, test } from "@playwright/test";
import { acceptWhenSettled, currentStep, openWizard } from "./helpers";

test("simulator banner, live readout and Space capture on the calibrate screen", async ({ page }) => {
  const mounted = await openWizard(page);
  test.skip(!mounted, "wizard shell is not mounted in App.tsx yet (see docs/e2e.md, Known gaps)");

  await page.keyboard.press("Enter"); // leave Setup
  expect(await currentStep(page)).toContain("Calibrate");
  await expect(page.getByTestId("sim-banner")).toHaveText("SIMULATED DATA");
  await expect(page.getByTestId("readout")).toContainText("Live V:");
  await expect(page.getByTestId("live-canvas")).toBeVisible();
  await acceptWhenSettled(page);
});

test("each capture phase shows its heading and accepts a point", async ({ page }) => {
  const mounted = await openWizard(page);
  test.skip(!mounted, "wizard shell is not mounted in App.tsx yet (see docs/e2e.md, Known gaps)");

  await page.keyboard.press("Enter");
  for (const [phase, heading] of [["Calibrate", /Calibrate/], ["Tare", /Tare/], ["Elastic", /Elastic/], ["Plastic", /Plastic/]] as const) {
    expect(await currentStep(page)).toContain(phase);
    await expect(page.getByRole("heading", { name: heading })).toBeVisible();
    await acceptWhenSettled(page);
    await page.keyboard.press("Enter");
  }
});
