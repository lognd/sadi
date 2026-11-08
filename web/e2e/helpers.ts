// frob:ticket 01M6W7RB9Q00GBJ5CJ0GW7ER11
// creates:web/e2e/helpers.ts
import { expect, type Page } from "@playwright/test";

/** Open the app and return whether the wizard shell is mounted (the step rail exists). */
export async function openWizard(page: Page): Promise<boolean> {
  await page.goto("/");
  await expect(page.locator("main, nav").first()).toBeVisible();
  // The backend has no /api/health route yet, so the app opens Doctor on load; close it to reach the wizard.
  const closeDoctor = page.getByRole("button", { name: "Close Doctor" });
  if (await closeDoctor.waitFor({ state: "visible", timeout: 5_000 }).then(() => true, () => false)) await closeDoctor.click();
  // With no open session the Setup screen offers a form; create a fresh session (never resume or discard one).
  const setup = page.getByRole("region", { name: "Session setup" });
  if (await setup.waitFor({ state: "visible", timeout: 5_000 }).then(() => true, () => false)) {
    const create = setup.getByRole("button", { name: "Create session" });
    // No labs registered (launcher does not wire the plugin labs yet): the form cannot submit; skip.
    if (!(await create.isEnabled({ timeout: 5_000 }).catch(() => false))) return false;
    await setup.getByLabel("Specimen name").fill("e2e specimen");
    await create.press("Enter");
  }
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

/** Wait (retrying) until the current rail step contains `text`; avoids racing the async wizard write. */
export async function expectStep(page: Page, text: string): Promise<void> {
  await expect(page.locator('ol.step-rail li[aria-current="step"]')).toContainText(text);
}

/** Wait until the live view reports Settled, then press Space (keyboard-only accept). */
export async function acceptWhenSettled(page: Page): Promise<void> {
  await expect(page.getByTestId("readout")).toContainText("[Settled]", { timeout: 60_000 });
  await page.keyboard.press(" ");
  await expect(page.getByTestId("run-message")).toContainText("Captured");
}

/** Leave the Setup step via "Skip this step": Setup needs captured clamp-check points and has no capture UI yet. */
export async function skipSetup(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Skip this step" }).click();
  await expect(page.locator('ol.step-rail li[aria-current="step"]')).not.toContainText("Setup");
}
