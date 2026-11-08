// frob:ticket 01M6X9NXTD91A49K5KE81EQRYA
// frob:ticket 01M6W7R41EVGYTSV1B72ZQVKAB
import type { RailItem } from "./types";

/** Props of the panel. */
export interface NextActionProps {
  step: RailItem | null;
  busy: boolean;
  canSkip: boolean;
  onPrimary: () => void;
  onSkip: () => void;
}

/** Big next-action panel: one sentence and one primary button for the current step. */
export function NextActionPanel({ step, busy, canSkip, onPrimary, onSkip }: NextActionProps): React.JSX.Element {
  return (
    <aside id="next-action" aria-label="Next action">
      <h2>Next action</h2>
      {step === null ? (
        <p>All steps are finished.</p>
      ) : (
        <>
          <p>{step.hint !== "" ? step.hint : `Work on: ${step.title}.`}</p>
          <button type="button" disabled={busy} onClick={onPrimary} style={{ fontSize: "1.5em" }}>
            Finish {step.title} (Enter)
          </button>
          {canSkip ? (
            <p>
              <button type="button" disabled={busy} onClick={onSkip}>Skip this step</button>
            </p>
          ) : null}
        </>
      )}
    </aside>
  );
}
