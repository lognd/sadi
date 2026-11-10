// frob:ticket 01M71RCHHEM9EKV4SAEYTVC4WD
// frob:accept COV001 because="test helper used by vitest suites; TypeScript test discovery needs grimble, not installed here"
import { deriveLive, type LiveView } from "../screens/run/live";
import type { RunLive, SideState } from "../screens/run/useRunLive";
import { TraceWindow } from "../plots/live";
import type { ConnState } from "../ws/client";
import { LiveContext } from "./LiveContext";

/** Build a RunLive value for tests: empty trace, open connection, overridable view and side state. */
export function fakeLive(o: { view?: Partial<LiveView>; side?: Partial<SideState>; conn?: ConnState } = {}): RunLive {
  const conn: ConnState = o.conn ?? { status: "open" };
  const snapshot = new TraceWindow(5, 0).snapshot(0);
  const side: SideState = { settle: null, rawSeq: 0, pointIndex: null, driftVps: null, window: null, simulated: false, ...o.side };
  const view = { ...deriveLive(snapshot, conn, side.settle, side.simulated, side.driftVps), ...o.view };
  return { snapshot, conn, notice: null, view, side };
}

/** Wrap an element in a LiveContext carrying a fake feed (no socket is opened). */
export function withLive(el: React.JSX.Element, live: RunLive = fakeLive()): React.JSX.Element {
  return <LiveContext.Provider value={live}>{el}</LiveContext.Provider>;
}
