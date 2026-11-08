// frob:ticket 01M6W7RB9Q00GBJ5CJ0GW7ER11
// creates:web/e2e/helpers.ts
import { expect, type Page } from "@playwright/test";

/** Open the app and return whether the wizard shell is mounted (the step rail exists). */
export async function openWizard(page: Page): Promise<boolean> {
  await page.goto("/");
  await expect(page.locator("main, nav").first()).toBeVisible();
  try {
    await page.getByRole("navigation", { name: "Steps" }).waitFor({ state: "visible", timeout: 10_000 });
    return true;
  } catch {
    return false;
  }
}

/** Title of the step currently marked aria-current in the rail. */
export async function currentStep(page: Page): Promise<string> {
  const li = page.locator('ol.step-rail li[aria-current="step"]');
  await expect(li).toHaveCount(1);
  return (await li.innerText()).replace(/\s+/g, " ");
}

/** Wait until the live view reports Settled, then press Space (keyboard-only accept). */
export async function acceptWhenSettled(page: Page): Promise<void> {
  await expect(page.getByTestId("readout")).toContainText("[Settled]", { timeout: 60_000 });
  await page.keyboard.press(" ");
  await expect(page.getByTestId("run-message")).toContainText("Captured");
}
