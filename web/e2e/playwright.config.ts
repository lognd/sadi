// frob:ticket 01M6W7RB9Q00GBJ5CJ0GW7ER11
// creates:web/e2e/playwright.config.ts
import { defineConfig } from "@playwright/test";

/** Playwright config: chromium only, one worker, backend per test comes from fixtures.ts. */
export default defineConfig({
  testDir: ".",
  testMatch: "*.spec.ts",
  workers: 1,
  fullyParallel: false,
  timeout: 540_000,
  reporter: [["list"]],
  use: { acceptDownloads: true, trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { browserName: "chromium" } }],
});
