// frob:ticket 01M727VHZTQHYABYCT6XTASEM1
// frob:ticket 01M6W7R41EVGYTSV1B72ZQVKAB
// frob:ticket 01M71XGJ7JM6YWRWCPMTRQJ0A5
import type { SaveView } from "./saveView";
/** Where readings come from. */
export type Source = "connected" | "simulated" | "faulted" | "disconnected";
/** Settle detector verdict (a suggestion only). */
export type Motion = "settled" | "creeping" | "unknown";
/** Input saturation level. */
export type Signal = "ok" | "near-limit" | "saturated";

/** Status bar inputs. */
export interface StatusBarProps {
  source: Source;
  motion: Motion;
  signal: Signal;
  /** The one save indicator (from saveView over the polled backend facts). */
  save: SaveView;
}

const SOURCE: Record<Source, string> = { connected: "Connected", simulated: "Simulated", faulted: "Faulted", disconnected: "Disconnected" };
const MOTION: Record<Motion, string> = { settled: "Settled", creeping: "Creeping", unknown: "Measuring..." };
const SIGNAL: Record<Signal, string> = { ok: "Signal OK", "near-limit": "Near limit", saturated: "SATURATED" };
const GLYPH = (bad: boolean): string => (bad ? "(!)" : "(ok)");

/** Always-visible status bar: source, motion, signal, save state; word plus glyph, never colour alone. */
export function StatusBar({ source, motion, signal, save }: StatusBarProps): React.JSX.Element {
  const off = source === "disconnected";
  return (
    <div role="status" aria-label="Status">
      <span data-indicator="source">{GLYPH(source === "disconnected" || source === "faulted")} {SOURCE[source]}</span>{" "}
      <span data-indicator="motion">{off ? "--" : GLYPH(motion === "creeping")} {off ? "No signal" : MOTION[motion]}</span>{" "}
      <span data-indicator="signal">{off ? "--" : GLYPH(signal !== "ok")} {off ? "No signal" : SIGNAL[signal]}</span>{" "}
      <span data-indicator="saved" data-state={save.state}>{save.state === "saved" ? "[ok]" : save.state === "saving" ? "[..]" : "(!)"} {save.text}</span>
    </div>
  );
}
