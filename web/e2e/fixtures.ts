// frob:ticket 01M6X3AVN6BF2D1RNPYDKZDSBS 01M703DQZDPX25NNXNSM0V8HB2
// Per-test backend: each test gets its own `sadi --sim` on a fresh temp data dir and port, so sessions never leak between specs.
import { spawn, type ChildProcess } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { test as base } from "@playwright/test";

const here = import.meta.dirname;
const py = resolve(here, "..", "..", "python");
const dist = resolve(here, "..", "dist");
let nextPort = Number(process.env.SADI_E2E_PORT ?? "8765");

/** Return the first bindable loopback port at or above the running counter (and advance it). */
async function freePort(): Promise<number> {
  for (;;) {
    const port = nextPort++;
    const ok = await new Promise<boolean>((done) => {
      const srv = createServer();
      srv.once("error", () => {
        done(false);
      });
      srv.listen(port, "127.0.0.1", () => {
        srv.close(() => {
          done(true);
        });
      });
    });
    if (ok) return port;
  }
}

/** Poll /openapi.json until the backend answers or the child exits / the deadline passes. */
async function waitReady(url: string, child: ChildProcess): Promise<void> {
  const deadline = Date.now() + 120_000;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) throw new Error(`sadi exited early with ${String(child.exitCode)}`);
    if (await fetch(`${url}/openapi.json`).then((r) => r.ok, () => false)) return;
    await new Promise((r) => setTimeout(r, 250));
  }
  throw new Error("backend did not become ready within 120 s");
}

/** Stop the backend; on Windows kill the whole tree because `child.kill` only ends the `uv` launcher and orphans python (which keeps the data-dir lock). */
async function stopBackend(child: ChildProcess): Promise<void> {
  const exited = new Promise<void>((r) => {
    if (child.exitCode !== null) r();
    else child.once("exit", () => {
      r();
    });
  });
  if (process.platform === "win32" && child.pid !== undefined) {
    await new Promise<void>((r) => {
      spawn("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore" }).once("close", () => {
        r();
      });
    });
  } else {
    child.kill("SIGTERM");
  }
  await exited;
}

/** Playwright `test` whose `baseURL` points at a private backend started and torn down per test. */
export const test = base.extend({
  // Playwright requires fixtures to destructure their first argument, even when empty.
  // eslint-disable-next-line no-empty-pattern
  baseURL: async ({}, use) => {
    const port = await freePort();
    const dataDir = mkdtempSync(join(tmpdir(), "sadi-e2e-")); // temp only; real data dirs are never touched
    const url = `http://127.0.0.1:${String(port)}`;
    const child = spawn(
      "uv",
      ["run", "--no-sync", "--project", py, "sadi", "--sim", "--no-browser", "--skip-preflight", "--port", String(port), "--data-dir", dataDir, "--web-dist", dist],
      { stdio: "inherit" },
    );
    try {
      await waitReady(url, child);
      await use(url);
    } finally {
      await stopBackend(child);
      // Windows can hold the data-dir lock for a moment after the process tree dies, so retry the removal.
      rmSync(dataDir, { recursive: true, force: true, maxRetries: 20, retryDelay: 250 });
    }
  },
});

export { expect } from "@playwright/test";
