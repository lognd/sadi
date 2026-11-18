// frob:ticket 01M6W7R41EVGYTSV1B72ZQVKAB
import { plainNote } from "./plainText";
import type { WizardFailure } from "./wizardApi";

/** Render a failure as what happened plus what to do (docs/ux.md section 6). */
export function ErrorNotice({ failure }: { failure: WizardFailure }): React.JSX.Element {
  if (failure.kind === "problem") {
    const { title, detail, hint } = failure.problem;
    return (
      <div role="alert">
        <p>! {plainNote(detail !== "" ? detail : title)}</p>
        <p>What to do: {hint !== "" ? hint : "See the server log for details."}</p>
      </div>
    );
  }
  return (
    <div role="alert">
      <p>! Could not reach the SADI backend.</p>
      <p>What to do: check that the app is running, then open Doctor.</p>
    </div>
  );
}
