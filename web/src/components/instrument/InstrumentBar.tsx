// frob:ticket 01M71SKWW36NDBJK24QD7DHSW4
// frob:accept COV001 because="covered by instrument.test.tsx (vitest); TypeScript test discovery needs grimble, not installed here"
import { useLive } from "../../state/LiveContext";
import type { LiveView } from "../../screens/run/live";
import type { ConnState } from "../../ws/client";
import { displacementMm, useCalibration, type Calib } from "./calibration";

const NOT_CAL = "not calibrated yet";

/** Settle state as glyph plus word. */
export function settleWord(v: LiveView): string {
  if (v.motion === "settled") return "[ok] Settled";
  if (v.motion === "unknown") return "[..] Measuring";
  return "(!) Creeping";
}

/** Connection state as glyph plus word. */
export function connWord(v: LiveView, conn: ConnState): string {
  if (conn.status === "reconnecting") return `(!) Reconnecting #${String(conn.attempt)}`;
  if (conn.status === "connecting") return "[..] Connecting";
  return v.source === "disconnected" ? "(!) Disconnected" : v.source === "simulated" ? "[ok] Simulated" : "[ok] Connected";
}

/** Presentational instrument bar: volts, displacement, load, drift, settle, connection and a SIMULATED banner. */
export function InstrumentBarView({ view, conn, calib }: { readonly view: LiveView; readonly conn: ConnState; readonly calib: Calib | null }): React.JSX.Element {
  const volts = view.volts === null ? "--" : view.volts.toFixed(4);
  const disp = calib === null || view.volts === null ? NOT_CAL : `${displacementMm(calib, view.volts).toFixed(3)} mm`;
  const drift = view.driftVps === null ? "--" : `${(view.driftVps * 1000).toFixed(1)} mV/s`;
  return (
    <section className="instrument-bar" aria-label="Instrument" data-stale={view.stale ? "true" : "false"}>
      {view.source === "simulated" && <p className="sim-banner" role="status" data-testid="sim-banner">SIMULATED DATA - not from the instrument</p>}
      <dl className="ib-grid">
        <div className="ib-big"><dt>LVDT</dt><dd data-testid="ib-volts"><span className="ib-num">{volts}</span> V</dd></div>
        <div className="ib-big"><dt>Displacement</dt><dd data-testid="ib-disp" data-cal={calib === null ? "no" : "yes"}>{disp}</dd></div>
        <div className="ib-big"><dt>Load</dt><dd data-testid="ib-load" data-cal="no">set by hanger mass</dd></div>
        <div><dt>Drift</dt><dd data-testid="ib-drift">{drift}</dd></div>
        <div><dt>Settle</dt><dd data-testid="ib-settle" data-state={view.motion}>{settleWord(view)}</dd></div>
        <div><dt>Signal</dt><dd data-testid="ib-signal" data-state={view.stale ? "stale" : view.signal}>{view.stale ? "(!) Stale" : view.signal === "ok" ? "[ok] OK" : view.signal === "saturated" ? "(!) SATURATED" : "(!) Near limit"}</dd></div>
        <div><dt>Connection</dt><dd data-testid="ib-conn" data-state={view.source}>{connWord(view, conn)}</dd></div>
      </dl>
    </section>
  );
}

/** Always-on instrument bar fed from the shared LiveProvider. */
export function InstrumentBar(): React.JSX.Element {
  const { view, conn } = useLive();
  return <InstrumentBarView view={view} conn={conn} calib={useCalibration()} />;
}
