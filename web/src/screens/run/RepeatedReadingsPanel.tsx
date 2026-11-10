// frob:ticket 01M72YKF3EN8RJX7RCH78JDPQC
import { useState } from "react";
import { parseReadings, summarizeReadings } from "./repeatedReadings";

/** Props: `unit` labels the readings; `onUse` receives mean and U95 to fill the value and uncertainty fields. */
export interface RepeatedReadingsPanelProps {
  readonly label: string;
  readonly unit: string;
  readonly onUse: (mean: number, u95: number) => void;
}

/** Operator types 3-5 repeated readings plus instrument U and sees mean, sd and the RSS uncertainty. */
export function RepeatedReadingsPanel(p: RepeatedReadingsPanelProps): React.JSX.Element {
  const [text, setText] = useState("");
  const [uInst, setUInst] = useState("0");
  const parsed = text.trim() === "" ? null : parseReadings(text);
  const summary = parsed?.ok === true ? summarizeReadings(parsed.value, Number(uInst.trim() === "" ? "0" : uInst)) : null;
  return (
    <details data-testid="repeated-readings">
      <summary>Repeated readings of {p.label}</summary>
      <label className="field">
        Readings ({p.unit}){" "}
        <input type="text" name="readings" value={text} onChange={(e) => { setText(e.target.value); }} />
      </label>
      <label className="field">
        Instrument uncertainty ({p.unit}){" "}
        <input type="text" inputMode="decimal" name="u_inst" value={uInst} onChange={(e) => { setUInst(e.target.value); }} />
      </label>
      {parsed?.ok === false && <p role="alert" data-testid="readings-error">{parsed.error}</p>}
      {summary?.ok === false && <p role="alert" data-testid="readings-error">{summary.error}</p>}
      {summary?.ok === true && (
        <p data-testid="readings-summary">
          n = {summary.value.n}, mean = {summary.value.mean.toPrecision(6)} {p.unit}, s = {summary.value.sd.toPrecision(3)} {p.unit},
          U95 = sqrt((t s / sqrt n)^2 + Uinst^2) = {summary.value.u95.toPrecision(3)} {p.unit}{" "}
          <button type="button" onClick={() => { p.onUse(summary.value.mean, summary.value.u95); }}>Use as value and uncertainty</button>
        </p>
      )}
    </details>
  );
}
