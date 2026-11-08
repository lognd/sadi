// frob:ticket 01M6WVQC0SQR7CMCB3V921XDAW
// Playwright config for the opt-in docs screenshot spec; reuses the per-test backend fixture from ../e2e.
import { defineConfig } from "@playwright/test";

/** Config for regenerating docs/img/ui: chromium, one worker, backend per test from ../e2e/fixtures.ts. */
export default defineConfig({
  testDir: ".",
  testMatch: "*.spec.ts",
  workers: 1,
  fullyParallel: false,
  timeout: 540_000,
  reporter: [["list"]],
  projects: [{ name: "chromium", use: { browserName: "chromium" } }],
});
