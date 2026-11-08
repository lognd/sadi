import { useEffect } from "react";
import { getHealth } from "./api/client";
import { getLogger } from "./api/log";
import { useStore } from "./state/store";

const log = getLogger("App");

// frob:accept COV001 because="vitest tests exist (src/App.test.tsx, src/api/log.test.ts) but TypeScript test discovery needs grimble, not installed here"
/** Root component: probes the backend and shows connection state. */
export function App(): React.JSX.Element {
  const connection = useStore((s) => s.connection);
  const setConnection = useStore((s) => s.setConnection);

  useEffect(() => {
    void getHealth().then((r) => {
      log.info("health probed", { ok: r.ok });
      setConnection(r.ok ? "up" : "down");
    });
  }, [setConnection]);

  return <main>SADI - backend: {connection}</main>;
}
