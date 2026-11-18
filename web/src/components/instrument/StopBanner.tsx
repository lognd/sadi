// frob:ticket 01M7274EH583A30335TGGT6ZZ1
import { useState } from "react";
import { postReconnect, postResume } from "../../api/client";
import { getLogger } from "../../api/log";
import type { BackendFacts } from "./useBackendFacts";

const log = getLogger("instrument.stop");

type Device = BackendFacts["device"];

/** Plain-language next step per stop reason; recorded data is always safe. */
const STEPS: Readonly<Record<string, string>> = {
  idle: "Live readings paused because nothing happened for a while. Your recorded data is safe. Press Resume live readings to start again; Mark load change is not needed to restart.",
  finished: "This run has finished recording. Your data is saved. To record more, Close the session, then Resume it.",
  low_disk: "Recording stopped because the computer is almost out of disk space. Your data so far is saved. Free some disk space, then Close the session and Resume it.",
  closed: "This session is closed. Your data is saved. Resume the session to record more.",
};

/** Banner text for a device's stop_reason / acquisition_fault, or null when streaming normally. */
export function stopMessage(d: Device): string | null {
  if (d === null) return null;
  if (d.acquisitionFault !== null && d.acquisitionFault !== "") {
    return `The instrument reported a problem: ${d.acquisitionFault}. Your recorded data is safe. Check the cable, then press Reconnect.`;
  }
  if (d.stopReason === null || d.stopReason === "") return null;
  return STEPS[d.stopReason] ?? `Live readings stopped (${d.stopReason}). Your recorded data is safe.`;
}

/** Why-it-stopped banner, shown whatever the connection source is. */
export function StopBanner({ device }: { readonly device: Device }): React.JSX.Element | null {
  const msg = stopMessage(device);
  if (msg === null) return null;
  const idle = device?.stopReason === "idle" && (device.acquisitionFault === null || device.acquisitionFault === "");
  return (
    <div className="ib-hint stop-banner" role="alert" data-testid="stop-banner" data-reason={device?.stopReason ?? "fault"}>
      <p>{msg}</p>
      {idle && <ResumeButton />}
    </div>
  );
}

// frob:ticket 01M727MMWZ8X2B29300XHTWZ46
/** Pull the operator hint out of a problem+json 409 body, falling back to a safe generic line. */
export function resumeHint(body: string): string {
  try {
    const j = JSON.parse(body) as { hint?: unknown; detail?: unknown };
    if (typeof j.hint === "string" && j.hint !== "") return j.hint;
    if (typeof j.detail === "string" && j.detail !== "") return j.detail;
  } catch {
    log.warn("resume error body was not JSON");
  }
  return "Could not resume live readings. Your data is safe; try again.";
}

/** Resume button: POSTs /api/acquisition/resume, disabled while pending, shows the 409 hint on failure. */
export function ResumeButton({ post = postResume }: { readonly post?: typeof postResume }): React.JSX.Element {
  const [pending, setPending] = useState(false);
  const [hint, setHint] = useState("");
  const click = (): void => {
    setPending(true);
    setHint("");
    void post().then((r) => {
      setPending(false);
      if (r.ok) {
        log.info("resume done", { streaming: r.value.streaming });
      } else {
        log.warn("resume failed", { kind: r.error.kind });
        setHint(r.error.kind === "http" ? resumeHint(r.error.body) : "Could not reach the instrument service. Your data is safe; try again.");
      }
    });
  };
  return (
    <span className="ib-resume" data-testid="ib-resume">
      <button type="button" onClick={click} disabled={pending} data-testid="ib-resume-btn">{pending ? "Resuming..." : "Resume live readings"}</button>
      {hint !== "" && <span role="status" data-testid="ib-resume-hint"> {hint}</span>}
    </span>
  );
}

/** True when a Reconnect makes sense for this device status. */
export function canReconnect(status: string | null): boolean {
  return status === "disconnected" || status === "error";
}

/** Reconnect button: POSTs /api/device/reconnect, disabled while pending, shows the returned hint. */
export function ReconnectButton({ status, post = postReconnect }: { readonly status: string | null; readonly post?: typeof postReconnect }): React.JSX.Element | null {
  const [pending, setPending] = useState(false);
  const [hint, setHint] = useState("");
  if (!canReconnect(status)) return null;
  const click = (): void => {
    setPending(true);
    setHint("");
    void post().then((r) => {
      setPending(false);
      if (r.ok) {
        log.info("reconnect done", { status: r.value.status });
        setHint(r.value.hint !== "" ? r.value.hint : r.value.attached ? "Instrument connected." : "No instrument found yet. Plug in the SADI board and try again.");
      } else {
        log.warn("reconnect failed", { kind: r.error.kind });
        setHint("Could not reach the instrument service. Your data is safe; try again.");
      }
    });
  };
  return (
    <div className="ib-reconnect" data-testid="ib-reconnect">
      <button type="button" onClick={click} disabled={pending} data-testid="ib-reconnect-btn">{pending ? "Reconnecting..." : "Reconnect"}</button>
      {hint !== "" && <span role="status" data-testid="ib-reconnect-hint"> {hint}</span>}
    </div>
  );
}
