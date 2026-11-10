// frob:ticket 01M71SKWW36NDBJK24QD7DHSW4
// frob:accept COV001 because="covered by wizard.test.tsx (vitest); TypeScript test discovery needs grimble, not installed here"
import { STEP_GUIDE } from "./stepGuide";

/** Instructions panel: short numbered actions, the field to watch, and the next step. */
export function DoThisCard({ phase, index, total }: { readonly phase: string; readonly index: number; readonly total: number }): React.JSX.Element | null {
  const g = STEP_GUIDE[phase];
  if (g === undefined) return null;
  return (
    <section className="do-this" aria-label="Do this">
      <h2>Do this <span className="do-step">Step {index + 1} of {total} - {g.next.replace(/^Next: /, "next: ")}</span></h2>
      <ol>{g.doThis.map((l) => <li key={l}>{l}</li>)}</ol>
      <p className="where-to-look"><strong>Where to look:</strong> {g.watch}</p>
    </section>
  );
}
