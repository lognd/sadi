// frob:ticket 01M6W7R41EVGYTSV1B72ZQVKAB
import type { RailItem, StepStatus } from "./types";

const GLYPH: Record<StepStatus, string> = { done: "[x]", skipped: "[-]", current: "[>]", locked: "[ ]" };
const WORD: Record<StepStatus, string> = { done: "done", skipped: "skipped", current: "current", locked: "upcoming" };

/** Persistent step rail: glyph plus word per step, aria-current on the current one. */
export function StepRail({ rail }: { rail: readonly RailItem[] }): React.JSX.Element {
  return (
    <nav aria-label="Steps">
      <ol className="step-rail">
        {rail.map((s, i) => (
          <li
            key={s.id}
            data-status={s.status}
            aria-current={s.status === "current" ? "step" : undefined}
            style={s.status === "current" ? { fontWeight: "bold", border: "1px solid" } : undefined}
          >
            <span aria-hidden="true">{GLYPH[s.status]}</span> {i + 1}. {s.title}{" "}
            <span className="sr-word">({WORD[s.status]})</span>
            {s.status === "skipped" && s.hint !== "" ? <em> {s.hint}</em> : null}
          </li>
        ))}
      </ol>
    </nav>
  );
}
