// frob:ticket 01M6X9NXRHXGBXA9YPKJAZDW9B
// frob:ticket 01M6X9Y0CWQ6YRMDT8QF5JD036
// creates:web/e2e/keyboard-only.spec.ts
// Keyboard-only walkthrough: Tab to a control, then Enter/Space to activate it (docs/usability-report.md, ~0MZ866N).
// Selectors use role + name patterns so label tweaks on the screens do not break them.
import { expect, test } from "./fixtures";
import { expectStep, inputsFor, openWizard } from "./helpers";
import type { Locator, Page } from "@playwright/test";

/** Press Tab until `target` holds focus (bounded, wraps through the page); never clicks or focuses by script. */
async function tabTo(page: Page, target: Locator, maxTabs = 120): Promise<void> {
  await expect(target.first()).toBeVisible();
  for (let i = 0; i < maxTabs; i += 1) {
    if (await target.first().evaluate((el) => el === document.activeElement)) return;
    await page.keyboard.press("Tab");
  }
  throw new Error(`Tab never reached the control within ${String(maxTabs)} presses`);
}

/** Tab to `target` and activate it with `key` ("Enter" or "Space"). */
async function activate(page: Page, target: Locator, key: "Enter" | "Space"): Promise<void> {
  await tabTo(page, target);
  await page.keyboard.press(key);
}

/** Reach a row action: Tab to the row's single tab stop, then Left/Right arrows until `target` holds focus. */
async function reachInRow(page: Page, target: Locator): Promise<void> {
  const row = target.first().locator("xpath=ancestor::*[@role='group'][1]");
  await tabTo(page, row.locator('button[tabindex="0"]'));
  for (const key of ["ArrowRight", "ArrowLeft", "ArrowRight"]) {
    if (await target.first().evaluate((el) => el === document.activeElement)) return;
    await page.keyboard.press(key);
  }
  await expect(target.first()).toBeFocused();
}

/** Reach a row action via the roving stop and activate it with `key`. */
async function activateInRow(page: Page, target: Locator, key: "Enter" | "Space"): Promise<void> {
  await reachInRow(page, target);
  await page.keyboard.press(key);
}

/** Type the capture inputs with the keyboard (Tab into each field), leaving focus on the last field. */
async function typeInputs(page: Page, values: Record<string, string>): Promise<void> {
  for (const [name, value] of Object.entries(values)) {
    const field = page.locator(`fieldset input[name="${name}"]`);
    await tabTo(page, field);
    await page.keyboard.type(value);
  }
}

/** One capture point using only Tab + Enter/Space: type inputs, mark load change, wait Settled, accept. */
async function captureByKeyboard(page: Page, phase: string, i: number, markKey: "Enter" | "Space"): Promise<void> {
  await typeInputs(page, inputsFor(phase, i));
  await activate(page, page.getByRole("button", { name: "Mark load change" }), markKey);
  await expect(page.getByTestId("run-message")).toContainText("Load change marked");
  await expect(page.getByTestId("readout")).not.toContainText("[Settled]", { timeout: 10_000 }).catch(() => undefined);
  await expect(page.getByTestId("readout")).toContainText("[Settled]", { timeout: 60_000 });
  await activate(page, page.getByRole("button", { name: /\(Space\)$/ }), "Space");
  await expect(page.getByTestId("run-message")).toContainText("Captured", { timeout: 120_000 });
}

test("guided run Setup -> Export using only Tab and Enter/Space", async ({ page }) => {
  const mounted = await openWizard(page);
  test.skip(!mounted, "wizard shell did not mount (is the backend up? see docs/e2e.md)");

  await expectStep(page, "Setup");
  await activate(page, page.getByRole("button", { name: /skip/i }), "Enter"); // Skip via Tab + Enter
  for (const phase of ["LVDT calibration", "Tare", "Elastic", "Plastic"]) {
    await expectStep(page, phase);
    const points = phase === "LVDT calibration" || phase === "Plastic" ? 3 : 1;
    for (let i = 0; i < points; i += 1) await captureByKeyboard(page, phase, i, i % 2 === 0 ? "Enter" : "Space");
    await activate(page, page.getByRole("button", { name: /^finish/i }), "Enter"); // finish the phase
  }

  await expectStep(page, "Results");
  const review = page.getByRole("region", { name: "Review" });
  const exclude = review.getByRole("button", { name: /^exclude /i }).first();
  const excludeName = (await exclude.innerText()).replace(/^exclude /i, "");
  await activateInRow(page, exclude, "Enter");
  const include = review.getByRole("button", { name: new RegExp(`^include ${excludeName}$`, "i") });
  await expect(include).toBeVisible();
  await activateInRow(page, include, "Space"); // put the point back
  await expect(review.getByRole("button", { name: new RegExp(`^exclude ${excludeName}$`, "i") })).toBeVisible();
  const edit = review.getByRole("button", { name: new RegExp(`^edit ${excludeName}$`, "i") });
  await activateInRow(page, edit, "Enter");
  await expect(edit).toHaveAttribute("aria-pressed", "true");
  await activate(page, page.getByRole("button", { name: /^finish/i }), "Space"); // advance to Export

  await expectStep(page, "Export");
  const link = page.getByRole("link", { name: /download/i }).first();
  await tabTo(page, link);
  const download = page.waitForEvent("download");
  await page.keyboard.press("Enter");
  expect((await download).suggestedFilename()).toMatch(/\.csv$/i);
});
