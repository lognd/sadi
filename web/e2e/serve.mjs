// frob:ticket 01M6W7RB9Q00GBJ5CJ0GW7ER11
// creates:web/e2e/serve.mjs
// Starts `sadi --sim` against a throwaway data dir so e2e never touches real session data.
import { spawn } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const port = process.env.SADI_E2E_PORT ?? "8765";
const dataDir = mkdtempSync(join(tmpdir(), "sadi-e2e-"));
const dist = resolve(import.meta.dirname, "..", "dist");
const py = resolve(import.meta.dirname, "..", "..", "python");
const log = (msg) => process.stderr.write(`[e2e-serve] ${msg}\n`);
log(`temp data dir ${dataDir} (never a real data dir)`);

const child = spawn(
  "uv",
  ["run", "--project", py, "sadi", "--sim", "--no-browser", "--skip-preflight", "--port", port, "--data-dir", dataDir, "--web-dist", dist],
  { stdio: "inherit" },
);
child.on("exit", (code) => {
  log(`sadi exited with ${String(code)}`);
  process.exit(code ?? 1);
});
for (const sig of ["SIGINT", "SIGTERM"]) {
  process.on(sig, () => child.kill(sig));
}
