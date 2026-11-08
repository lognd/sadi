// frob:ticket 01M6W7RB0GPGHTABW7P4XEGRNJ
// frob:accept COV001 because="covered by results-stream.test.tsx (vitest); TypeScript test discovery needs grimble, not installed here"
/** Component showing one streamed result with a stale marker and a refinement progress bar. */
import type { ReactElement } from "react";
import type { StreamState } from "./store";
import { isRefining, isStale } from "./store";

/** Props: stream state, result key and a formatter for the opaque value payload. */
export interface StreamedValueProps {
  readonly state: StreamState;
  readonly name: string;
  readonly format: (value: unknown) => string;
}

/** Render a result; never shows a lagging value without the stale marker. */
export function StreamedValue({ state, name, format }: StreamedValueProps): ReactElement {
  const e = state.byKey[name];
  if (e === undefined) return <span data-testid="streamed-pending">pending</span>;
  const stale = isStale(state, e);
  const refining = isRefining(state, e);
  const pct = Math.round(e.progress * 100);
  return (
    <span data-testid="streamed-value" data-data-version={e.dataVersion} data-result-version={e.resultVersion}>
      <span>{format(e.value)}</span>
      {stale ? <span data-testid="stale-marker" title={`computed from data v${String(e.dataVersion)}; newer data exists`}> (stale)</span> : null}
      {refining ? (
        <progress data-testid="refine-progress" value={pct} max={100} aria-label={`refining ${name}`}>{pct}%</progress>
      ) : null}
    </span>
  );
}
