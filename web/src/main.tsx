// frob:ticket 01M6XAASPRSYNWC5K5MH77E8KJ
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./styles.css";
import { getLogger } from "./api/log";
import { watchStickyTop } from "./hooks/useStickyOffset";

const log = getLogger("main");
const root = document.getElementById("root");
if (!root) {
  log.error("missing #root element");
  throw new Error("missing #root element");
}
log.info("mounting app");
createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
// frob:ticket 01M72855X7J5P97BAN234Z81W4
watchStickyTop(() => root.querySelector<HTMLElement>(".app-top"));
