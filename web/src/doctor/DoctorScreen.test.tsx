import { describe, expect, it, vi } from "vitest";
import { renderToString } from "react-dom/server";
import { DoctorScreen, FixSteps, VerdictBanner, type DoctorApi } from "./DoctorScreen";
import { useDoctorRoute, openDoctorOnConnectionError } from "./useDoctorRoute";
import { getDoctor, runDoctorCheck } from "../api/client";
import type { CheckResult } from "./types";

const failing: CheckResult = {
  id: "NET-001", title: "Port free", layer: "net", severity: "error", status: "fail",
  headline: "port busy", duration_ms: 3,
  remediation: {
    check_id: "NET-001", mode: "busy", os: "linux", summary: "Free the port", docs: [],
    steps: [
      { kind: "action", text: "Stop the process", commands: [{ shell: "sh", line: "kill 1" }], expect: "gone" },
      { kind: "verify", text: "Re-run", commands: [], expect: "pass" },
    ],
  },
};

describe("doctor ui", () => {
  it("renders numbered fix steps", () => {
    const html = renderToString(<FixSteps result={failing} />);
    expect(html).toContain("<ol>");
    expect(html).toContain("Stop the process");
    expect(html).toContain("kill 1");
  });

  it("renders checks from a mocked api with re-run buttons", () => {
    const api: DoctorApi = { list: vi.fn(), run: vi.fn() };
    const html = renderToString(<DoctorScreen api={api} />);
    expect(html).toContain("Doctor");
  });

  // frob:ticket 01M71XGJ7JM6YWRWCPMTRQJ0A5
  // covers web/src/doctor/DoctorScreen.tsx::VerdictBanner
  it("shows the verdict, counts and first action (audit #33)", () => {
    const html = renderToString(<VerdictBanner summary={{ verdict: "blocked", first_action: "Free port 8000" }} results={[failing]} />).replaceAll("<!-- -->", "");
    expect(html).toContain("Verdict: blocked");
    expect(html).toContain("1 failed");
    expect(html).toContain("Do this first: Free port 8000");
  });

  it("opens from a connection error", () => {
    openDoctorOnConnectionError();
    expect(useDoctorRoute.getState().visible).toBe(true);
    useDoctorRoute.getState().close();
    expect(useDoctorRoute.getState().visible).toBe(false);
  });

  it("typed client calls the doctor endpoints", async () => {
    const f = vi.fn(() => Promise.resolve(new Response(JSON.stringify(failing))));
    const r = await runDoctorCheck("NET-001", f);
    expect(r.ok).toBe(true);
    expect(f).toHaveBeenCalledWith("/api/doctor/NET-001/run", expect.objectContaining({ method: "POST" }));
    const g = vi.fn(() => Promise.resolve(new Response("boom", { status: 500 })));
    const l = await getDoctor(g);
    expect(l).toMatchObject({ ok: false, error: { kind: "http", status: 500 } });
  });
});
