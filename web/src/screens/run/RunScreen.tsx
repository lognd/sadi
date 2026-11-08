// frob:ticket 01M6W7RB7ZFKF3DVKWW74FQXWT
// frob:ticket 01M6WWN96C55R68VNZF2D1NB2V
// frob:accept COV001 because="covered by RunScreen.test.tsx (vitest); TypeScript test discovery needs grimble, not installed here"
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getLogger } from "../../api/log";
import { WizardShell } from "../../components/wizard/WizardShell";
import type { KeyAction } from "../../keys/keymap";
import type { UseTraceOptions } from "../../hooks/useTrace";
import { renderToCanvas } from "../../plots/core";
import { buildLiveScene } from "../../plots/live";
import type { ConnState } from "../../ws/client";
import type { Snapshot } from "../../plots/live";
import { DEFAULT_RUN_EXPORT, exportErrorText, fetchRunExport } from "./exportTrace";
import { buildBody, decide, postCapture, type Confirm } from "./capture";
import type { RunPhase } from "./phases";
import { RunView, type PhasePlot } from "./RunView";
import { useRunLive } from "./useRunLive";

const log = getLogger("screens.run");

/** Canvas drawing the shared live scene from the screen's single stream subscription (no second socket). */
export function TraceCanvas({ snapshot, conn }: { readonly snapshot: Snapshot; readonly conn: ConnState }): React.JSX.Element {
  const scene = useMemo(() => buildLiveScene(snapshot, { conn }), [snapshot, conn]);
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => { if (ref.current) renderToCanvas(ref.current, scene); }, [scene]);
  return <canvas ref={ref} data-testid="live-canvas" aria-label={scene.title} />;
}

/** Save a blob through a temporary link; browser only. */
function saveBlob(blob: Blob, name: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

/** Props of the run screen. */
export interface RunScreenProps {
  readonly phase: RunPhase;
  /** True when the source is the simulator (status bar and banner). */
  readonly simulated?: boolean;
  /** Phase plot data, fed by the host after each capture. */
  readonly plot?: PhasePlot | null;
  /** Typed inputs sent with a capture (voltage-independent: length, mass, ...). */
  readonly inputs?: Readonly<Record<string, unknown>>;
  /** Called after the server accepted a capture. */
  readonly onCaptured?: () => void;
  readonly trace?: UseTraceOptions;
  /** Server export format F3 downloads (default lctt-csv). */
  readonly exportFormat?: string;
  /** Receives the downloaded export; the default saves it through a temporary link (browser only). */
  readonly onExport?: (blob: Blob, filename: string) => void;
  readonly fetchImpl?: typeof fetch;
}

/** Live run screen for calibrate, tare, elastic and plastic: wizard shell, live trace, accept key, confirmation. */
export function RunScreen(p: RunScreenProps): React.JSX.Element {
  const live = useRunLive({ ...p.trace, simulated: p.simulated ?? false });
  const [confirm, setConfirm] = useState<Confirm>("idle");
  const [message, setMessage] = useState<string | null>(null);
  const { view, side } = live;
  const preview = decide(view, false, "idle");
  const blockedWhy = preview.kind === "blocked" ? preview.why : null;

  const capture = useCallback(async (early: boolean): Promise<void> => {
    const r = await postCapture(buildBody(p.phase, p.inputs ?? {}, side.rawSeq, view, early), p.fetchImpl);
    setConfirm("idle");
    if (r.ok) { setMessage(`Captured: ${r.value.summary}`); p.onCaptured?.(); }
    else setMessage(r.error.kind === "network" ? `Network error: ${r.error.message}. Check the connection, then try again.` : `Capture refused (HTTP ${String(r.error.status)}). ${r.error.body}`);
  }, [p, side.rawSeq, view]);

  const accept = useCallback((early: boolean): void => {
    const d = decide(view, early, confirm);
    log.info("accept", { early, decision: d.kind });
    if (d.kind === "blocked") { setMessage(d.why); setConfirm("idle"); }
    else if (d.kind === "confirm-early") setConfirm("asking");
    else void capture(d.kind === "capture-early");
  }, [view, confirm, capture]);

  const doExport = useCallback(async (): Promise<void> => {
    const r = await fetchRunExport(p.exportFormat ?? DEFAULT_RUN_EXPORT, p.fetchImpl);
    if (!r.ok) { setMessage(exportErrorText(r.error)); return; }
    (p.onExport ?? saveBlob)(r.value.blob, r.value.filename);
    setMessage(`Exported ${r.value.filename}`);
    log.info("exported", { filename: r.value.filename });
  }, [p]);

  const onKey = useCallback((a: KeyAction): void => {
    if (a === "accept") accept(false);
    else if (a === "accept-unsettled") accept(true);
    else if (a === "cancel") setConfirm("idle");
    else if (a === "export") void doExport();
  }, [accept, doExport]);

  return (
    <WizardShell status={{ source: view.source, motion: view.motion, signal: view.signal }} onKeyAction={onKey}>
      {p.simulated === true && <p data-testid="sim-banner">SIMULATED DATA</p>}
      <RunView
        phase={p.phase} view={view} trace={<TraceCanvas snapshot={live.snapshot} conn={live.conn} />} plot={p.plot ?? null}
        blockedWhy={blockedWhy} confirming={confirm === "asking"} message={message ?? live.notice}
        onAccept={() => { accept(false); }} onConfirmEarly={() => { accept(true); }}
        onCancelEarly={() => { setConfirm("idle"); }}
      />
    </WizardShell>
  );
}
