import { describe, expect, it } from "vitest";

import config from "../vite.config";

// frob:ticket ~TSXXK8B
// frob:tests web/vite.config.ts
describe("vite dev proxy", () => {
  it("proxies /api with websocket upgrade to the launcher default port", () => {
    const proxy = config.server?.proxy as Record<string, { target: string; ws?: boolean }>;
    expect(proxy["/api"]?.ws).toBe(true);
    expect(proxy["/api"]?.target).toBe("http://127.0.0.1:8000");
  });
});
