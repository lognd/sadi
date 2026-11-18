// frob:ticket 01M71RCHHEM9EKV4SAEYTVC4WD
import type { LiveView } from "../../screens/run/live";

/** Text for the creep/settle indicator, with drift rate when known. */
export function settleText(v: LiveView): string {
  if (v.motion === "settled") return "[Settled]";
  if (v.motion === "unknown") return "[Measuring...]";
  return v.driftVps === null ? "[Creeping]" : `[Creeping ${Math.abs(v.driftVps * 1000).toFixed(1)} mV/s]`;
}
