// frob:ticket 01M6WMGMJE0WEXXNQ3AD754A8M
import { useCallback, useRef, useState } from "react";
import { getLogger } from "../api/log";
import { refitModulus } from "../api/refit";
import type { ApiError } from "../api/client";
import { StressStrainPlot } from "../plots/stressstrain/StressStrainPlot";
import type { FitWindow, StressStrainData } from "../plots/stressstrain/model";

const log = getLogger("screens.stressstrain");

/** Outcome of one refit attempt: the data to show and an error message if the refit failed. */
export interface RefitOutcome {
  readonly data: StressStrainData;
  readonly error: string | null;
}

/** Human-readable message for an API failure. */
export function describeError(e: ApiError): string {
  return e.kind === "network" ? `Network error: ${e.message}` : `Refit failed (HTTP ${String(e.status)}): ${e.body}`;
}

/** Refit over `w`; on success swap in the new fit, on failure keep `data` (points and previous fit) intact. */
export async function applyRefit(
  data: StressStrainData,
  w: FitWindow,
  fetchImpl: typeof fetch = fetch,
): Promise<RefitOutcome> {
  const r = await refitModulus(w, fetchImpl);
  if (!r.ok) {
    log.warn("refit failed; keeping previous fit", { window: w, kind: r.error.kind });
    return { data, error: describeError(r.error) };
  }
  log.info("refit applied", { window: w, eGpa: r.value.eGpa, r2: r.value.r2 });
  return { data: { ...data, fit: { ...r.value, first: w.first, last: w.last } }, error: null };
}

/** Props: the captured data and an optional fetch (injected in tests). */
export interface StressStrainScreenProps {
  readonly initial: StressStrainData;
  readonly fetchImpl?: typeof fetch;
}

/** Host screen: wires the plot's onWindowChange to the API refit and re-renders E, r^2 and uncertainty. */
export function StressStrainScreen({ initial, fetchImpl }: StressStrainScreenProps): React.JSX.Element {
  const [data, setData] = useState(initial);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const seq = useRef(0);
  const latest = useRef(data);
  latest.current = data;

  const onWindowChange = useCallback((w: FitWindow): void => {
    const id = ++seq.current;
    setBusy(true);
    void applyRefit(latest.current, w, fetchImpl).then((o) => {
      if (id !== seq.current) return; // a newer window superseded this reply
      setData(o.data);
      setError(o.error);
      setBusy(false);
    });
  }, [fetchImpl]);

  const fit = data.fit;
  return (
    <section aria-label="Stress-strain">
      <StressStrainPlot data={data} onWindowChange={onWindowChange} />
      {fit !== null && (
        <p data-testid="fit-summary">
          {`E = ${fit.eGpa.toFixed(2)} +/- ${fit.eU95Gpa.toFixed(2)} GPa, r^2 = ${fit.r2.toFixed(4)}`}
          {fit.lowR2 ? " (low r^2)" : ""}{busy ? " (refitting...)" : ""}
        </p>
      )}
      {error !== null && <p role="alert">{error}</p>}
    </section>
  );
}
