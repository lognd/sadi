// frob:ticket 01M71SKWW36NDBJK24QD7DHSW4
/** Live displacement from the fitted calibration; null until calibration and tare exist. */
import { useEffect, useState } from "react";
import { getJson } from "../../api/client";
import type { ResultSet } from "../results/types";

/** Calibration slope (m per volt) and tare (volts), or null when not captured yet. */
export interface Calib { readonly slope: number; readonly tare: number }

/** Pick slope and tare from a result set; null if either is missing. */
export function calibFrom(r: ResultSet): Calib | null {
  const v = (n: string): number | undefined => r.values.find((x) => x.name === n)?.value;
  const slope = v("slope");
  const tare = v("tare");
  return slope === undefined || tare === undefined ? null : { slope, tare };
}

/** Displacement in mm for a volts reading under a calibration. */
export function displacementMm(c: Calib, volts: number): number {
  return c.slope * (volts - c.tare) * 1000;
}

/** Poll the results endpoint for calibration and tare. */
export function useCalibration(pollMs = 3000): Calib | null {
  const [c, setC] = useState<Calib | null>(null);
  useEffect(() => {
    let live = true;
    const tick = (): void => { void getJson<ResultSet>("/api/results").then((r) => { if (live) setC(r.ok ? calibFrom(r.value) : null); }); };
    tick();
    const id = setInterval(tick, pollMs);
    return () => { live = false; clearInterval(id); };
  }, [pollMs]);
  return c;
}
