// frob:ticket 01M6X3AVN6BF2D1RNPYDKZDSBS
// frob:ticket 01M703DQZDPX25NNXNSM0V8HB2
// frob:ticket 01M709DXGS91GPWZ3M06FWXJPY
// frob:ticket 01M713J4YBWW0CZ9B7DBKQZGMH
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

/** Ask the OS for a free loopback port (bind port 0), so worker restarts never replay a stale counter. */
async function freePort(): Promise<number> {
  return new Promise<number>((resolvePort, reject) => {
    const srv = createServer();
    srv.once("error", reject);
    srv.listen(0, "127.0.0.1", () => {
      const addr = srv.address();
      const port = typeof addr === "object" && addr !== null ? addr.port : 0;
      srv.close(() => {
        resolvePort(port);
      });
    });
  });
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

/** Stop the backend and its whole process tree (taskkill on Windows, process-group signal elsewhere) because killing only the `uv` launcher orphans python, which keeps the port and the data-dir lock. */
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
  } else if (child.pid !== undefined) {
    // The child leads its own process group (detached), so signal the group: `uv` may not forward to python.
    try {
      process.kill(-child.pid, "SIGTERM");
    } catch {
      child.kill("SIGTERM"); // group already gone
    }
    const forced = setTimeout(() => {
      try {
        process.kill(-(child.pid ?? 0), "SIGKILL");
      } catch {
        /* already exited */
      }
    }, 10_000);
    await exited;
    clearTimeout(forced);
    return;
  }
  await exited;
}

/** Playwright `test` whose `baseURL` points at a private backend started and torn down per test. */
export const test = base.extend<{ dataDir: string }>({
  // The per-test temp data dir (never a real one); torn down after the backend that locks it.
  // eslint-disable-next-line no-empty-pattern
  dataDir: async ({}, use) => {
    const dir = mkdtempSync(join(tmpdir(), "sadi-e2e-"));
    try {
      await use(dir);
    } finally {
      // Windows can hold the data-dir lock for a moment after the process tree dies, so retry the removal.
      rmSync(dir, { recursive: true, force: true, maxRetries: 20, retryDelay: 250 });
    }
  },
  baseURL: async ({ dataDir }, use) => {
    const port = await freePort();
    const url = `http://127.0.0.1:${String(port)}`;
    const child = spawn(
      "uv",
      ["run", "--no-sync", "--project", py, "sadi", "--sim", "--no-browser", "--skip-preflight", "--port", String(port), "--data-dir", dataDir, "--web-dist", dist],
      { stdio: "inherit", detached: process.platform !== "win32" },
    );
    try {
      await waitReady(url, child);
      await use(url);
    } finally {
      await stopBackend(child);
    }
  },
});

export { expect } from "@playwright/test";
