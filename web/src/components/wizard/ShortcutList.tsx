// frob:ticket 01M6W7R41EVGYTSV1B72ZQVKAB
import { SHORTCUTS } from "../../keys/keymap";

/** On-screen list of keyboard shortcuts. */
export function ShortcutList(): React.JSX.Element {
  return (
    <dl aria-label="Keyboard shortcuts">
      {SHORTCUTS.map((s) => (
        <div key={s.keys}>
          <dt>{s.keys}</dt>
          <dd>{s.label}</dd>
        </div>
      ))}
    </dl>
  );
}
