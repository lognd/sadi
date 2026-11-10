// frob:ticket 01M72ZDQGAN0VQRKHM489H28J1
import { useEffect, useState } from "react";
import { getLogger } from "../../api/log";
import { getPoints } from "../../screens/review/api";
import { inputText, pointFlags, shortId } from "../../screens/review/ReviewScreen";
import type { PointView } from "../../screens/review/types";
import type { RailItem } from "./types";

const log = getLogger("wizard.stepdata");

const PHASE_MATCH: Readonly<Record<string, RegExp>> = {
  calibration: /cal/i,
  plastic: /yield|plastic/i,
};

/** Captured points that belong to a rail step (matched by phase name; setup and other non-capture steps have none). */
export function pointsForStep(points: readonly PointView[], step: RailItem): PointView[] {
  const re = PHASE_MATCH[step.phase] ?? new RegExp(`^${step.phase}$`, "i");
  return points.filter((p) => re.test(p.phase));
}

/** Presentational read-only table of a step's captured points: no capture, edit or advance controls. */
export function StepDataView({ step, points }: { step: RailItem; points: readonly PointView[] | null }): React.JSX.Element {
  if (points === null) return <p data-testid="step-data-loading">Loading {step.title} data...</p>;
  const mine = pointsForStep(points, step);
  if (mine.length === 0) return <p data-testid="step-data-empty">No data was captured for {step.title}.</p>;
  return (
    <section aria-label={`${step.title} data`} data-testid="step-data">
      <h3>{step.title} data (read-only)</h3>
      <table>
        <thead><tr><th>Point</th><th>Inputs</th><th>Flags</th></tr></thead>
        <tbody>
          {mine.map((p) => (
            <tr key={p.point_id}>
              <td>{shortId(p.point_id)}</td>
              <td>{Object.entries(p.inputs).map(([k, v]) => `${k}=${inputText(v)}`).join(", ")}</td>
              <td>{pointFlags(p)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

/** Loads the stored points once and shows the given step's data read-only. */
export function StepData({ step, fetchImpl }: { step: RailItem; fetchImpl?: typeof fetch }): React.JSX.Element {
  const [points, setPoints] = useState<PointView[] | null>(null);
  useEffect(() => {
    let live = true;
    void getPoints(fetchImpl).then((r) => {
      if (!live) return;
      if (r.ok) setPoints(r.value);
      else { log.warn("step data load failed", { step: step.id }); setPoints([]); }
    });
    return () => { live = false; };
  }, [step.id, fetchImpl]);
  return <StepDataView step={step} points={points} />;
}
