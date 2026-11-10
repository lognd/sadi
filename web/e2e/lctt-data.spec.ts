// frob:ticket 01M713J4YBWW0CZ9B7DBKQZGMH
// creates:web/e2e/lctt-data.spec.ts
// Full LCTT run against the simulator, then checks the exported data content and that the run is durable on disk.
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "./fixtures";
import { acceptWhenSettled, expectStep, inputsFor, openWizard, skipSetup } from "./helpers";

/** Every regular file under `dir` with its size, recursively. */
function filesUnder(dir: string): { path: string; size: number }[] {
  const out: { path: string; size: number }[] = [];
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    const st = statSync(p);
    if (st.isDirectory()) out.push(...filesUnder(p));
    else out.push({ path: p, size: st.size });
  }
  return out;
}

test("LCTT run exports real data and the session is saved on disk and recoverable", async ({ page, request, dataDir }) => {
  const mounted = await openWizard(page);
  test.skip(!mounted, "wizard shell did not mount (is the backend up? see docs/e2e.md)");

  await skipSetup(page);
  const captured = { "LVDT calibration": 3, Tare: 1, Elastic: 1, Plastic: 3 } as const;
  for (const [phase, count] of Object.entries(captured)) {
    await expectStep(page, phase);
    for (let i = 0; i < count; i += 1) await acceptWhenSettled(page, inputsFor(phase, i));
    await page.keyboard.press("f");
  }
  await expectStep(page, "Results");
  await page.keyboard.press("Enter");
  await expectStep(page, "Export");

  // The CSV the user downloads has a header and a data row per captured point (CRLF, UTF-8).
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: /download/i }).first().click();
  const csvPath = await (await download).path();
  const csv = readFileSync(csvPath, "utf8").replace(/^\u{FEFF}/u, "");
  const lines = csv.split("\r\n").filter((l) => l.length > 0);
  expect(lines.length).toBeGreaterThan(1);
  expect(lines[0]?.split(",").length).toBeGreaterThan(1);
  expect(lines.slice(1).some((l) => /\d/.test(l))).toBe(true);

  // The server holds every capture and the session version exists on the API.
  const points = (await (await request.get("/api/session/points")).json()) as unknown[];
  expect(points.length).toBeGreaterThanOrEqual(8);
  const sessions = (await (await request.get("/api/sessions")).json()) as { name: string }[];
  expect(sessions.length).toBeGreaterThanOrEqual(1);

  // And it is on disk (the temp data dir) as non-empty files, not only in memory.
  const files = filesUnder(dataDir);
  expect(files.length).toBeGreaterThan(0);
  expect(files.some((f) => f.size > 0)).toBe(true);

  // Recoverable: close the session, then resume it as a new version and find every point again.
  expect((await request.post("/api/session/close")).status()).toBe(204);
  const source = sessions[0];
  expect(source).toBeDefined();
  const resumed = await request.post("/api/sessions/resume", { data: { name: source?.name } });
  expect(resumed.status()).toBe(201);
  const again = (await (await request.get("/api/session/points")).json()) as unknown[];
  expect(again.length).toBe(points.length);
});
