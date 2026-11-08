// frob:ticket 01M6W7RB9Q00GBJ5CJ0GW7ER11
// creates:web/e2e/playwright.config.ts
import { defineConfig } from "@playwright/test";

const port = process.env.SADI_E2E_PORT ?? "8765";

/** Playwright config: chromium only, one worker, backend started in simulator mode on a temp data dir. */
export default defineConfig({
  testDir: ".",
  testMatch: "*.spec.ts",
  workers: 1,
  fullyParallel: false,
  timeout: 120_000,
  reporter: [["list"]],
  use: { baseURL: `http://127.0.0.1:${port}`, acceptDownloads: true, trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { browserName: "chromium" } }],
  webServer: {
    command: "node e2e/serve.mjs",
    cwd: "..",
    url: `http://127.0.0.1:${port}/openapi.json`,
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
