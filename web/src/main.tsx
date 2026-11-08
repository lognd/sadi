import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { getLogger } from "./api/log";

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
