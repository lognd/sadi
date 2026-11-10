// frob:ticket 01M6W7R41EVGYTSV1B72ZQVKAB
// frob:ticket 01M71RCHHEM9EKV4SAEYTVC4WD
import { useCallback, useEffect, useRef, useState } from "react";
import { getLogger } from "../../api/log";
import { useKeyCapture } from "../../keys/useKeyCapture";
import type { KeyAction } from "../../keys/keymap";
import { useLive } from "../../state/LiveContext";
import { LiveReadout } from "../live/LiveReadout";
import { LiveTrace } from "../live/TraceCanvas";
import { StatusBar } from "../status/StatusBar";
import { ErrorNotice } from "./ErrorNotice";
import { FrontPanel } from "./FrontPanel";
import { NextActionPanel } from "./NextActionPanel";
import { ShortcutList } from "./ShortcutList";
import { StepRail } from "./StepRail";
import type { WizardState } from "./types";
import { getWizard, postWizard, type WizardFailure, type WizardWrite } from "./wizardApi";

const log = getLogger("wizard.shell");

/** Shell props: work-area content comes from the step screens; live status comes from LiveProvider. */
export interface WizardShellProps {
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
/** Wizard shell: the front panel (step rail, step content, next action, live readout, live trace, status bar) plus keyboard capture. */
export function WizardShell({ children, onKeyAction, nudgeActive = false, onWizard, delegateUndo = false }: WizardShellProps): React.JSX.Element {
  const { view } = useLive();
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

  const index = wizard === null || current === null ? -1 : wizard.rail.indexOf(current);
  const title = wizard === null ? "Guided run" : current === null ? "All steps finished" : current.title;
  const subtitle = wizard === null || current === null ? null : `Step ${String(index + 1)} of ${String(wizard.rail.length)}`;

  return (
    <FrontPanel
      title={title}
      subtitle={subtitle}
      rail={wizard ? <StepRail rail={wizard.rail} /> : <p>Loading steps...</p>}
      shortcuts={help ? <ShortcutList /> : null}
      live={<><LiveReadout /><LiveTrace /></>}
      status={<StatusBar source={view.source} motion={view.motion} signal={view.signal} savedAt={savedAt} />}
      next={
        <NextActionPanel
          step={current}
          busy={busy}
          canSkip={current !== null}
          onPrimary={() => { void write("wizard/complete"); }}
          onSkip={() => { void write("wizard/skip"); }}
        />
      }
    >
      {failure ? <ErrorNotice failure={failure} /> : null}
      {children}
    </FrontPanel>
  );
}
