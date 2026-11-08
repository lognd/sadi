// frob:ticket 01M6W7R41EVGYTSV1B72ZQVKAB
/** Where readings come from. */
export type Source = "connected" | "simulated" | "disconnected";
/** Settle detector verdict (a suggestion only). */
export type Motion = "settled" | "creeping" | "unknown";
/** Input saturation level. */
export type Signal = "ok" | "near-limit" | "saturated";

/** Status bar inputs. */
export interface StatusBarProps {
  source: Source;
  motion: Motion;
  signal: Signal;
  /** Wall-clock text of the last durable save, or null when nothing was saved yet. */
  savedAt: string | null;
}

const SOURCE: Record<Source, string> = { connected: "Connected", simulated: "Simulated", disconnected: "Disconnected" };
const MOTION: Record<Motion, string> = { settled: "Settled", creeping: "Creeping", unknown: "Measuring..." };
const SIGNAL: Record<Signal, string> = { ok: "Signal OK", "near-limit": "Near limit", saturated: "SATURATED" };
const GLYPH = (bad: boolean): string => (bad ? "(!)" : "(ok)");

/** Always-visible status bar: source, motion, signal, save time; word plus glyph, never colour alone. */
export function StatusBar({ source, motion, signal, savedAt }: StatusBarProps): React.JSX.Element {
  return (
    <div role="status" aria-label="Status">
      <span data-indicator="source">{GLYPH(source === "disconnected")} {SOURCE[source]}</span>{" "}
      <span data-indicator="motion">{GLYPH(motion === "creeping")} {MOTION[motion]}</span>{" "}
      <span data-indicator="signal">{GLYPH(signal !== "ok")} {SIGNAL[signal]}</span>{" "}
      <span data-indicator="saved">{savedAt === null ? "Not saved yet" : `Saved ${savedAt}`}</span>
    </div>
  );
}
