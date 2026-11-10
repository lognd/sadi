// frob:ticket 01M6W7R41EVGYTSV1B72ZQVKAB
import { useCallback, useEffect, useRef, useState } from "react";
import { getLogger } from "../../api/log";
import { useKeyCapture } from "../../keys/useKeyCapture";
import type { KeyAction } from "../../keys/keymap";
import { StatusBar, type StatusBarProps } from "../status/StatusBar";
import { ErrorNotice } from "./ErrorNotice";
import { NextActionPanel } from "./NextActionPanel";
import { ShortcutList } from "./ShortcutList";
import { StepRail } from "./StepRail";
import type { WizardState } from "./types";
import { getWizard, postWizard, type WizardFailure, type WizardWrite } from "./wizardApi";

const log = getLogger("wizard.shell");

/** Shell props: status inputs and work-area content come from the run screens. */
export interface WizardShellProps {
  status: Omit<StatusBarProps, "savedAt">;
  children?: React.ReactNode;
  /** Called for capture and window-nudge keys the shell does not handle itself. */
  onKeyAction?: (a: KeyAction) => void;
  nudgeActive?: boolean;
  /** Called whenever the rail is loaded or changes, so a host can pick the screen for the current step. */
  onWizard?: (w: WizardState) => void;
  /** When true, undo and redo keys go to `onKeyAction` instead of the shell (the work area owns history). */
  delegateUndo?: boolean;
}

// frob:accept COV001 because="vitest tests exist (wizard.test.tsx, keymap.test.ts) but TypeScript test discovery needs grimble, not installed here"
/** Wizard shell: rail, work area, next-action panel, status bar and keyboard capture. */
export function WizardShell({ status, children, onKeyAction, nudgeActive = false, onWizard, delegateUndo = false }: WizardShellProps): React.JSX.Element {
  const [wizard, setWizard] = useState<WizardState | null>(null);
  const [failure, setFailure] = useState<WizardFailure | null>(null);
  const [busy, setBusy] = useState(false);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [help, setHelp] = useState(true);
  const wizardCb = useRef(onWizard);
  wizardCb.current = onWizard;

  useEffect(() => {
    void getWizard().then((r) => {
      if (r.ok) { setWizard(r.value); wizardCb.current?.(r.value); }
      else { log.warn("wizard load failed"); setFailure(r.error); }
    });
  }, []);

  const currentId = wizard?.current ?? wizard?.rail.find((s) => s.status === "current")?.id;
  const write = useCallback(async (what: WizardWrite): Promise<void> => {
    setBusy(true);
    const stepped = what === "wizard/complete" || what === "wizard/skip" || what === "wizard/revert";
    const r = await postWizard(what, fetch, stepped ? currentId : undefined);
    setBusy(false);
    if (r.ok) {
      log.info("committed", { what, seq: r.value.seq });
      setWizard(r.value.wizard);
      wizardCb.current?.(r.value.wizard);
      setFailure(null);
      setSavedAt(new Date().toLocaleTimeString());
    } else {
      log.warn("write failed", { what });
      setFailure(r.error);
    }
  }, [currentId]);

  const current = wizard?.rail.find((s) => s.status === "current") ?? null;
  const act = useCallback((a: KeyAction): void => {
    log.debug("action", { a });
    if (a === "primary" || a === "finish-phase") void write("wizard/complete");
    else if (delegateUndo && (a === "undo" || a === "redo")) onKeyAction?.(a);
    else if (a === "undo") void write("undo");
    else if (a === "redo") void write("redo");
    else if (a === "help") setHelp((h) => !h);
    else onKeyAction?.(a);
  }, [write, onKeyAction, delegateUndo]);
  useKeyCapture(act, nudgeActive);

  return (
    <div>
      <h1>Guided run</h1>
      {wizard ? <StepRail rail={wizard.rail} /> : <p>Loading steps...</p>}
      <main>
        {failure ? <ErrorNotice failure={failure} /> : null}
        {children}
      </main>
      <NextActionPanel
        step={current}
        busy={busy}
        canSkip={current !== null}
        onPrimary={() => { void write("wizard/complete"); }}
        onSkip={() => { void write("wizard/skip"); }}
      />
      {help ? <ShortcutList /> : null}
      <StatusBar {...status} savedAt={savedAt} />
    </div>
  );
}
