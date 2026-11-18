// frob:ticket 01M7274EH583A30335TGGT6ZZ1
// frob:ticket 01M71SKWW36NDBJK24QD7DHSW4
// frob:ticket 01M71VN3JDC5NDPJ2AW60KQX63
// frob:ticket 01M71XGJ7JM6YWRWCPMTRQJ0A5
// frob:accept COV001 because="covered by instrument.test.tsx (vitest); TypeScript test discovery needs grimble, not installed here"
import { SyntheticBanner } from "../provenance/SyntheticBanner";
import type { DataProvenance } from "../../state/provenance";
import { useLive } from "../../state/LiveContext";
import type { LiveView } from "../../screens/run/live";
import type { ConnState } from "../../ws/client";
import type { BackendFacts } from "./useBackendFacts";
import { StopBanner, ReconnectButton } from "./StopBanner";
import { displacementMm, useCalibration, type Calib } from "./calibration";

const NOT_CAL = "not calibrated yet";

/** Settle state as glyph plus word. */
export function settleWord(v: LiveView): string {
  if (v.source === "disconnected") return "-- no signal";
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
export function InstrumentBarView({ view, conn, calib, provenance, deviceHint, device, noFrames }: { readonly view: LiveView; readonly conn: ConnState; readonly calib: Calib | null; readonly provenance?: DataProvenance | null; readonly deviceHint?: string; readonly device?: BackendFacts["device"]; readonly noFrames?: boolean }): React.JSX.Element {
  const off = view.source === "disconnected";
  const volts = view.volts === null ? "--" : view.volts.toFixed(4);
  const disp = calib === null || view.volts === null ? NOT_CAL : `${displacementMm(calib, view.volts).toFixed(3)} mm`;
  const drift = view.driftVps === null ? "--" : `${(view.driftVps * 1000).toFixed(1)} mV/s`;
  return (
    <section className="instrument-bar" aria-label="Instrument" data-stale={view.stale ? "true" : "false"}>
      <SyntheticBanner provenance={provenance} />
      {view.source === "simulated" && <p className="sim-banner" role="status" data-testid="sim-banner">SIMULATED DATA - not from the instrument</p>}
      {off && <p className="ib-hint" role="status" data-testid="ib-hint">{deviceHint !== undefined && deviceHint !== "" ? deviceHint : "Instrument not connected: plug in the instrument."}</p>}
      <StopBanner device={device ?? null} />
      <ReconnectButton status={device?.status ?? null} />
      <dl className="ib-grid">
        <div className="ib-big"><dt>LVDT</dt><dd data-testid="ib-volts"><span className="ib-num">{volts}</span> V</dd></div>
        <div className="ib-big"><dt>Displacement</dt><dd data-testid="ib-disp" data-cal={calib === null ? "no" : "yes"}>{disp}</dd></div>
        <div className="ib-big"><dt>Load</dt><dd data-testid="ib-load" data-cal="no">set by hanger mass</dd></div>
        <div><dt>Drift</dt><dd data-testid="ib-drift">{drift}</dd></div>
        <div><dt>Settle</dt><dd data-testid="ib-settle" data-state={view.motion}>{settleWord(view)}</dd></div>
        <div><dt>Signal</dt><dd data-testid="ib-signal" data-state={off ? "none" : noFrames === true ? "none" : view.stale ? "stale" : view.signal}>{off ? "-- no signal" : noFrames === true ? "[..] No data" : view.stale ? "(!) Stale" : view.signal === "ok" ? "[ok] OK" : view.signal === "saturated" ? "(!) SATURATED" : "(!) Near limit"}</dd></div>
        <div><dt>Connection</dt><dd data-testid="ib-conn" data-state={view.source}>{connWord(view, conn)}</dd></div>
      </dl>
    </section>
  );
}

/** Always-on instrument bar fed from the shared LiveProvider. */
export function InstrumentBar({ facts }: { readonly facts: BackendFacts }): React.JSX.Element {
  const { view, conn, meta } = useLive();
  return <InstrumentBarView view={view} conn={conn} calib={useCalibration()} deviceHint={facts.device?.hint ?? ""} device={facts.device} noFrames={meta === null} />;
}
