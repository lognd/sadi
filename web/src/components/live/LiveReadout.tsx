// frob:ticket 01M71RCHHEM9EKV4SAEYTVC4WD
// frob:accept COV001 because="covered by LiveReadout.test.tsx (vitest); TypeScript test discovery needs grimble, not installed here"
import { useLive } from "../../state/LiveContext";
import type { LiveView } from "../../screens/run/live";
import type { ConnState } from "../../ws/client";

const SIGNAL = { ok: "OK", "near-limit": "Near limit", saturated: "SATURATED" } as const;
const SOURCE = { connected: "Connected", simulated: "Simulated", faulted: "Faulted", disconnected: "Disconnected" } as const;

/** Settle state as glyph plus word (never colour alone). */
function settleWord(v: LiveView): string {
  if (v.motion === "settled") return "[ok] Settled";
  if (v.motion === "unknown") return "[..] Measuring...";
  return "(!) Creeping";
}

/** Connection state in plain words, with the reconnect attempt when retrying. */
function connWord(v: LiveView, conn: ConnState): string {
  if (conn.status === "reconnecting") return `(!) Reconnecting (attempt ${String(conn.attempt)})`;
  return `${v.source === "disconnected" || v.source === "faulted" ? "(!)" : "[ok]"} ${SOURCE[v.source]}`;
}

/** Presentational live readout card: big LVDT volts, drift, settle, signal, connection, SIMULATED banner. */
export function LiveReadoutView({ view, conn }: { readonly view: LiveView; readonly conn: ConnState }): React.JSX.Element {
  const drift = view.driftVps === null ? "--" : `${(view.driftVps * 1000).toFixed(1)} mV/s`;
  const signalBad = view.signal !== "ok";
  return (
    <section className="card live-readout" aria-label="Live readout" data-stale={view.stale ? "true" : "false"}>
      <h2>Live reading</h2>
      {view.source === "simulated" && (
        <p className="sim-banner" role="status" data-testid="sim-banner">SIMULATED DATA - not from the instrument</p>
      )}
      <p className="readout-value" data-testid="readout" aria-live="off">
        <span className="readout-num">{view.volts === null ? "--" : view.volts.toFixed(4)}</span>
        <span className="readout-unit"> V</span>
        <span className="readout-label"> LVDT</span>
      </p>
      <dl className="readout-grid">
        <div><dt>Drift</dt><dd data-testid="readout-drift">{drift}</dd></div>
        <div><dt>Settle</dt><dd data-testid="readout-settle" data-state={view.motion}>{settleWord(view)}</dd></div>
        <div>
          <dt>Signal</dt>
          <dd data-testid="readout-signal" data-state={view.stale ? "stale" : view.signal}>
            {view.stale ? "(!) Stale - not current" : `${signalBad ? "(!)" : "[ok]"} ${SIGNAL[view.signal]}`}
          </dd>
        </div>
        <div><dt>Connection</dt><dd data-testid="readout-conn" data-state={view.source}>{connWord(view, conn)}</dd></div>
      </dl>
    </section>
  );
}

/** Live readout card fed from the shared LiveProvider. */
export function LiveReadout(): React.JSX.Element {
  const { view, conn } = useLive();
  return <LiveReadoutView view={view} conn={conn} />;
}
