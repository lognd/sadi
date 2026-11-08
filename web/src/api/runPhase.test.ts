// frob:ticket 01M6XAZ42NR9WARFYVZMS85NR2
import { describe, expect, it, vi } from "vitest";
import { enterRunPhase, getRunPhase, isServerPhase, postRunPhase } from "./runPhase";

const view = (phase: string | null, next: string | null): Response =>
  new Response(JSON.stringify({ phase, next_phase: next }), { status: 200 });
const refusal = (): Response =>
  new Response(JSON.stringify({ title: "bad_phase_transition", detail: "no", hint: "Enter elastic next." }), { status: 409 });

describe("runPhase", () => {
  it("knows which screens are server phases", () => {
    expect(isServerPhase("elastic")).toBe(true);
    expect(isServerPhase("tare")).toBe(false);
  });

  it("GETs and POSTs the phase body", async () => {
    const f = vi.fn().mockResolvedValueOnce(view("calibrate", "elastic")).mockResolvedValueOnce(view("elastic", "plastic"));
    expect((await getRunPhase(f)).ok).toBe(true);
    const r = await postRunPhase("elastic", f);
    expect(r.ok && r.value.phase).toBe("elastic");
    const init = f.mock.calls[1]?.[1] as RequestInit;
    expect(init.method).toBe("POST");
    expect(init.body).toBe('{"phase":"elastic"}');
  });

  it("repeating the current phase makes no POST", async () => {
    const f = vi.fn().mockResolvedValue(view("elastic", "plastic"));
    const r = await enterRunPhase("elastic", f);
    expect(r.ok).toBe(true);
    expect(f).toHaveBeenCalledTimes(1);
  });

  it("posts the next phase, and catches up through missing ones", async () => {
    const f = vi.fn()
      .mockResolvedValueOnce(view(null, "calibrate"))
      .mockResolvedValueOnce(view("calibrate", "elastic"))
      .mockResolvedValueOnce(view("elastic", "plastic"));
    const r = await enterRunPhase("elastic", f);
    expect(r.ok && r.value.phase).toBe("elastic");
    expect(f).toHaveBeenCalledTimes(3);
  });

  it("surfaces a 409 hint as a problem failure", async () => {
    const f = vi.fn().mockResolvedValueOnce(view("calibrate", "elastic")).mockResolvedValueOnce(refusal());
    const r = await enterRunPhase("elastic", f);
    expect(!r.ok && r.error.kind === "problem" && r.error.problem.hint).toBe("Enter elastic next.");
  });

  it("reports a network failure as transport", async () => {
    const r = await getRunPhase(vi.fn().mockRejectedValue(new Error("down")));
    expect(!r.ok && r.error.kind).toBe("transport");
  });
});
