// frob:ticket 01M6X9NXTD91A49K5KE81EQRYA
// frob:ticket 01M6W7R41EVGYTSV1B72ZQVKAB
// frob:ticket 01M6XAASPRSYNWC5K5MH77E8KJ
import type { RailItem } from "./types";

/** Props of the panel. */
export interface NextActionProps {
  step: RailItem | null;
  busy: boolean;
  canSkip: boolean;
  onPrimary: () => void;
  onSkip: () => void;
  /** Shown when all steps are finished (Close session, Start another). */
  finishedActions?: React.ReactNode;
}

/** Big next-action panel: one sentence and one primary button for the current step. */
export function NextActionPanel({ step, busy, canSkip, onPrimary, onSkip, finishedActions }: NextActionProps): React.JSX.Element {
  return (
    <aside id="next-action" aria-label="Next action">
      <h2>Next action</h2>
      {step === null ? (
        <>
          <p>All steps are finished.</p>
          {finishedActions}
        </>
      ) : (
        <>
          <p>{step.hint !== "" ? step.hint : `Work on: ${step.title}.`}</p>
          <button type="button" disabled={busy} onClick={onPrimary} className="btn btn-primary" data-variant="primary">
            Finish {step.title} (Enter)
          </button>
          {canSkip ? (
            <p>
              <button type="button" disabled={busy} onClick={onSkip} className="btn btn-secondary" data-variant="secondary">Skip this step</button>
            </p>
          ) : null}
        </>
      )}
    </aside>
  );
}
