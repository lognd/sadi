import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

/** Port of the FastAPI backend that the dev server proxies to. */
const API_PORT = process.env.SADI_API_PORT ?? "8000";
const API_TARGET = `http://127.0.0.1:${API_PORT}`;

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": { target: API_TARGET, changeOrigin: true },
      "/ws": { target: API_TARGET.replace("http", "ws"), ws: true },
    },
  },
  test: { environment: "node", include: ["src/**/*.test.{ts,tsx}"] },
});
