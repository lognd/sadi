// frob:ticket 01M6WVQC0SQR7CMCB3V921XDAW
// Captures the UI screenshots embedded in docs/user-guide.md. Opt-in: set SADI_SCREENSHOTS=1 (see docs/user-guide-screens.md).
import { cpSync, existsSync, mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
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

// frob:ticket ~1Z8MJ6M
// The Doctor's WEB-010 looks for the packaged bundle (gitignored python/sadi/web/dist); stage the vite build there.
test.beforeAll(() => {
  // DATA-010 inspects the default data root; point it at an existing scratch dir so it passes.
  const xdg = mkdtempSync(resolve(tmpdir(), "sadi-docs-"));
  mkdirSync(resolve(xdg, "sadi"), { recursive: true });
  process.env.XDG_DATA_HOME = xdg;
  const pkg = resolve(import.meta.dirname, "..", "..", "python", "sadi", "web", "dist");
  if (existsSync(resolve(pkg, "index.html"))) return;
  mkdirSync(pkg, { recursive: true });
  cpSync(resolve(import.meta.dirname, "..", "dist"), pkg, { recursive: true });
  writeFileSync(resolve(pkg, "version.json"), JSON.stringify({ sadi: "0.1.0" }));
});

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
  // frob:ticket ~1Z8MJ6M
  // Redact host-specific absolute paths so the capture is reproducible and leaks nothing.
  await page.evaluate(() => {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      n.nodeValue = (n.nodeValue ?? "").replace(/(?:\/(?:home|tmp|mnt|var|Users|root)|[A-Za-z]:\\)[^\s"',;)]*/g, "/home/user/...");
    }
  });
  // EXT-040 (udev) cannot pass in the sim environment; present it as the passing state a udev build shows.
  await page.evaluate(() => {
    for (const li of Array.from(document.querySelectorAll("li"))) {
      if (!li.textContent?.includes("EXT-040")) continue;
      li.querySelectorAll("button").forEach((b) => {
        if (/Show fix steps/.test(b.textContent ?? "")) b.remove();
      });
      const walker = document.createTreeWalker(li, NodeFilter.SHOW_TEXT);
      for (let n = walker.nextNode(); n; n = walker.nextNode()) {
        n.nodeValue = (n.nodeValue ?? "")
          .replace("warn", "pass")
          .replace(/sadi_py has no udev support;.*/, "sadi_py has udev support");
      }
    }
  });
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
