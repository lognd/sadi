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
  await expect(page.locator('ol.step-rail li[aria-current="step"]')).toContainText(text, { timeout: 120_000 });
}

/** Fill the Run screen capture inputs by field name (SI units); a blank volts field uses the live reading. */
export async function fillInputs(page: Page, values: Record<string, string>): Promise<void> {
  for (const [name, value] of Object.entries(values)) await page.locator(`fieldset input[name="${name}"]`).fill(value);
  // Hotkeys are ignored while a text field has focus (keys/useKeyCapture), so leave the field before pressing Space.
  await page.evaluate(() => { (document.activeElement as HTMLElement | null)?.blur(); });
}

/** Fill the given inputs, mark a load change, wait until Settled, then press Space (keyboard-only accept). */
export async function acceptWhenSettled(page: Page, inputs: Record<string, string> = {}): Promise<void> {
  await fillInputs(page, inputs);
  // The detector only leaves "loading" once a load change is marked (docs/e2e.md).
  await page.getByRole("button", { name: "Mark load change" }).click();
  // Wait for the marker ack so a stale "Captured" from the previous point cannot satisfy the final assertion.
  await expect(page.getByTestId("run-message")).toContainText("Load change marked");
  // The previous point's [Settled] may still be on screen; let the marker take effect first (best effort).
  await expect(page.getByTestId("readout")).not.toContainText("[Settled]", { timeout: 10_000 }).catch(() => undefined);
  await expect(page.getByTestId("readout")).toContainText("[Settled]", { timeout: 60_000 });
  await page.keyboard.press(" ");
  await expect(page.getByTestId("run-message")).toContainText("Captured", { timeout: 120_000 });
}

/** Leave the Setup step via "Skip this step": Setup needs captured clamp-check points and has no capture UI yet. */
export async function skipSetup(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Skip this step" }).click();
  await expect(page.locator('ol.step-rail li[aria-current="step"]')).not.toContainText("Setup");
}

/** Typed capture inputs for the `i`th point of a step (phase = rail title text); heights and masses rise with i. */
export function inputsFor(phase: string, i: number): Record<string, string> {
  const p = phase.toLowerCase();
  if (p.includes("calibration")) return { height: String(0.01 + 0.005 * i) };
  if (p.includes("tare")) return { n: "100" };
  return { mass_kg: String(0.1 * (i + 1)) };
}
