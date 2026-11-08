// frob:ticket ~DKZDSBS
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
      srv.once("error", () => done(false));
      srv.listen(port, "127.0.0.1", () => srv.close(() => done(true)));
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

/** Playwright `test` whose `baseURL` points at a private backend started and torn down per test. */
export const test = base.extend({
  baseURL: async ({}, use) => {
    const port = await freePort();
    const dataDir = mkdtempSync(join(tmpdir(), "sadi-e2e-")); // temp only; real data dirs are never touched
    const url = `http://127.0.0.1:${port}`;
    const child = spawn(
      "uv",
      ["run", "--project", py, "sadi", "--sim", "--no-browser", "--skip-preflight", "--port", String(port), "--data-dir", dataDir, "--web-dist", dist],
      { stdio: "inherit" },
    );
    try {
      await waitReady(url, child);
      await use(url);
    } finally {
      child.kill("SIGTERM");
      await new Promise((r) => (child.exitCode !== null ? r(null) : child.once("exit", r)));
      rmSync(dataDir, { recursive: true, force: true });
    }
  },
});

export { expect } from "@playwright/test";
