// frob:ticket 01M6XAASMZX11EZ5NYC3FNTQ6Z
// frob:ticket 01M6W7R41EVGYTSV1B72ZQVKAB
import type { RailItem, StepStatus } from "./types";

const GLYPH: Record<StepStatus, string> = { done: "[x]", skipped: "[-]", current: "[>]", locked: "[ ]" };
const WORD: Record<StepStatus, string> = { done: "done", skipped: "skipped", current: "current", locked: "upcoming" };

/** Persistent step rail: glyph plus word per step; only the current step is a tab stop (no jumping past gates), marked aria-current. */
export function StepRail({ rail }: { rail: readonly RailItem[] }): React.JSX.Element {
  return (
    <nav aria-label="Steps">
      <ol className="step-rail">
        {rail.map((s, i) => (
          <li
            key={s.id}
            data-status={s.status}
            aria-current={s.status === "current" ? "step" : undefined}
            tabIndex={s.status === "current" ? 0 : undefined}
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
