// frob:ticket 01M6WVQC0SQR7CMCB3V921XDAW
// Captures the UI screenshots embedded in docs/user-guide.md. Opt-in: set SADI_SCREENSHOTS=1 (see docs/user-guide-screens.md).
import { resolve } from "node:path";
import { expect, test } from "../e2e/fixtures";
import {
  acceptWhenSettled,
  expectStep,
  inputsFor,
  openWizard,
  skipSetup,
} from "../e2e/helpers";

const out = resolve(import.meta.dirname, "..", "..", "docs", "img", "ui");

test.skip(
  !process.env.SADI_SCREENSHOTS,
  "set SADI_SCREENSHOTS=1 to regenerate docs/img/ui",
);
test.use({ viewport: { width: 1000, height: 640 } });

test("capture user-guide screenshots against the simulator", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.locator("main, nav").first()).toBeVisible();
  // frob:ticket 01M6X8XTSNXF7EF647J8ZJZX7F
  // Doctor may already be open (backend has no health route); otherwise open it from the nav.
  const closeDoctor = page.getByRole("button", { name: "Close Doctor" });
  const alreadyOpen = await closeDoctor
    .waitFor({ state: "visible", timeout: 5_000 })
    .then(() => true, () => false);
  if (!alreadyOpen) await page.getByRole("button", { name: "Doctor", exact: true }).click();
  await expect(page.getByRole("main", { name: "Doctor" })).toBeVisible();
  await page.getByRole("button", { name: /^Re-run / }).first().waitFor({ state: "visible", timeout: 30_000 }); // checks loaded
  await page.screenshot({ path: `${out}/doctor.png` });
  await page.getByRole("button", { name: "Close Doctor" }).click();

  const mounted = await openWizard(page);
  test.skip(!mounted, "wizard shell did not mount");
  await expectStep(page, "Setup");
  await page.screenshot({ path: `${out}/setup.png` });
  await skipSetup(page);

  for (const phase of ["LVDT calibration", "Tare", "Elastic", "Plastic"]) {
    await expectStep(page, phase);
    const points = phase === "LVDT calibration" || phase === "Plastic" ? 3 : 1;
    for (let i = 0; i < points; i += 1) {
      await acceptWhenSettled(page, inputsFor(phase, i));
      if (i === 0 && phase === "LVDT calibration") {
        await page.evaluate(() => window.scrollTo(0, 0));
        await page.screenshot({ path: `${out}/run-capture.png` });
      }
    }
    await page.keyboard.press("f");
  }
  await expectStep(page, "Results");
  await page.screenshot({ path: `${out}/results.png` });
  await page.keyboard.press("Enter");
  await expectStep(page, "Export");
  await expect(page.getByRole("region", { name: /results/i })).toContainText(
    /secant_modulus/,
  );
  await page.screenshot({ path: `${out}/export.png` });
});
