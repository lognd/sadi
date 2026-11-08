// frob:ticket 01M6XA21KQE5WEXAN39683H4S9
// frob:accept COV001 because="covered by ClampCheckPanel.test.tsx (vitest); TypeScript test discovery needs grimble, not installed here"
import { useCallback, useEffect, useState } from "react";
import type { ApiError } from "../../api/client";
import { getLogger } from "../../api/log";
import { captureCycle, getClampStatus, parseCycle, type ClampStatus } from "./clampApi";

const log = getLogger("setup.clamp");

/** Operator text for a failed call. */
export function apiErrorText(e: ApiError): string {
  return e.kind === "network" ? `Network error: ${e.message}. Check the connection, then try again.` : `Server refused (HTTP ${String(e.status)}). ${e.body}`;
}

/** Presentational clamp-check view: procedure, cycle table, verdict and the cycle form. */
export function ClampCheckView(p: {
  readonly status: ClampStatus | null;
  readonly message: string;
  readonly busy: boolean;
  readonly onCapture: (f: { zeroBefore: string; zeroAfter: string; slips: string }) => void;
}): React.JSX.Element {
  const [zb, setZb] = useState("");
  const [za, setZa] = useState("");
  const [slips, setSlips] = useState("0");
  const s = p.status;
  const n = s?.cycles.length ?? 0;
  return (
    <section aria-label="Clamp slip check">
      <h2>Setup: Clamp slip check</h2>
      <p>This check finds loose clamps before the test, so slip is not mistaken for specimen strain.</p>
      <p>{s?.guidance ?? "Loading procedure..."}</p>
      <p>Cycles captured: {String(n)} of {String(s?.required ?? 0)}. Strain should return to its zero within {String(s?.return_tol ?? 0)}.</p>
      {n > 0 && s !== null ? (
        <ul aria-label="Captured cycles">
          {s.cycles.map((c) => (
            <li key={c.index}>Cycle {String(c.index + 1)}: zero shift {c.zero_shift.toExponential(2)}, slips {String(c.slip_events)} - {c.passed ? "ok" : "needs attention"}</li>
          ))}
        </ul>
      ) : null}
      {s?.passed != null ? <p role="status">{s.passed ? "Pass" : "Fail"}: {s.advice}</p> : null}
      <form aria-label="Capture cycle" onSubmit={(e) => { e.preventDefault(); if (!p.busy) p.onCapture({ zeroBefore: zb, zeroAfter: za, slips }); }}>
        <label>Zero before loading (strain){" "}<input value={zb} inputMode="decimal" onChange={(e) => { setZb(e.target.value); }} autoFocus /></label>{" "}
        <label>Zero after unloading (strain){" "}<input value={za} inputMode="decimal" onChange={(e) => { setZa(e.target.value); }} /></label>{" "}
        <label>Slips seen during hold{" "}<input value={slips} inputMode="numeric" onChange={(e) => { setSlips(e.target.value); }} /></label>{" "}
        <button type="submit" disabled={p.busy}>Capture cycle</button>
      </form>
      <p role="status">{p.message}</p>
      <p>Press Enter on the primary button when finished, or Skip this step to continue without the check. Captured cycles are never overwritten.</p>
    </section>
  );
}

/** Setup step body: loads the clamp status and captures each cycle through the points API. */
export function ClampCheckPanel({ fetchImpl }: { readonly fetchImpl?: typeof fetch }): React.JSX.Element {
  const [status, setStatus] = useState<ClampStatus | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback((): void => {
    void getClampStatus(fetchImpl).then((r) => {
      if (r.ok) setStatus(r.value);
      else { log.warn("clamp status failed", { kind: r.error.kind }); setMessage(apiErrorText(r.error)); }
    });
  }, [fetchImpl]);
  useEffect(() => { load(); }, [load]);

  const onCapture = useCallback((f: { zeroBefore: string; zeroAfter: string; slips: string }): void => {
    const parsed = parseCycle(f);
    if (!parsed.ok) { setMessage(parsed.error); return; }
    setBusy(true);
    void captureCycle(parsed.value, fetchImpl).then((r) => {
      setBusy(false);
      if (r.ok) { log.info("cycle captured"); setMessage(`Captured: ${r.value.summary}`); load(); }
      else setMessage(apiErrorText(r.error));
    });
  }, [fetchImpl, load]);

  return <ClampCheckView status={status} message={message} busy={busy} onCapture={onCapture} />;
}
