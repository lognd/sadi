// frob:ticket 01M7230XGWSR1B8D93KW5M4P7D
// frob:accept COV001 because="covered by wizard.test.tsx (vitest); TypeScript test discovery needs grimble, not installed here"
import { useCallback, useState } from "react";
import { getLogger } from "../../api/log";
import { useRefreshFacts } from "../instrument/FactsContext";
import { closeSession, type WizardFailure } from "./wizardApi";
import { ErrorNotice } from "./ErrorNotice";

const log = getLogger("wizard.close");

/** Confirmation text: closing stops recording but never deletes anything. */
export const CLOSE_CONFIRM_TEXT = "Close this session? All captured data stays saved in the session folder and you can open it again later.";

/** Presentational state of the close control. */
export interface CloseSessionViewProps {
  readonly label: string;
  readonly confirming: boolean;
  readonly busy: boolean;
  readonly failure: WizardFailure | null;
  readonly onAsk: () => void;
  readonly onConfirm: () => void;
  readonly onCancel: () => void;
}

/** Button that asks for confirmation before closing; shows the refusal when closing fails. */
export function CloseSessionView(p: CloseSessionViewProps): React.JSX.Element {
  return (
    <span className="close-session" data-testid="close-session">
      {p.confirming ? (
        <span role="alertdialog" aria-label="Confirm close session" data-testid="close-confirm">
          <span>{CLOSE_CONFIRM_TEXT}</span>
          <button type="button" disabled={p.busy} onClick={p.onConfirm} className="btn btn-primary">Yes, close session</button>
          <button type="button" disabled={p.busy} onClick={p.onCancel} className="btn btn-secondary">Keep working</button>
        </span>
      ) : (
        <button type="button" onClick={p.onAsk} className="btn btn-secondary">{p.label}</button>
      )}
      {p.failure ? <ErrorNotice failure={p.failure} /> : null}
    </span>
  );
}

/** Close-session control: confirms, POSTs /api/session/close, then calls `onClosed`. */
export function CloseSession({ label = "Close session", onClosed, fetchImpl = fetch }: {
  label?: string;
  onClosed: () => void;
  fetchImpl?: typeof fetch;
}): React.JSX.Element {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const refreshFacts = useRefreshFacts();
  const [failure, setFailure] = useState<WizardFailure | null>(null);
  const onConfirm = useCallback((): void => {
    setBusy(true);
    void closeSession(fetchImpl).then((r) => {
      setBusy(false);
      if (r.ok) { log.info("session closed from the page"); setConfirming(false); setFailure(null); refreshFacts(); onClosed(); }
      else { log.warn("close failed"); setFailure(r.error); }
    });
  }, [fetchImpl, onClosed, refreshFacts]);
  return (
    <CloseSessionView
      label={label}
      confirming={confirming}
      busy={busy}
      failure={failure}
      onAsk={() => { setConfirming(true); }}
      onConfirm={onConfirm}
      onCancel={() => { setConfirming(false); setFailure(null); }}
    />
  );
}
