import { renderToString } from "react-dom/server";
import { describe, expect, test } from "vitest";
import { App } from "./App";

describe("App", () => {
  test("renders the initial connection state", () => {
    expect(renderToString(<App />)).toContain("backend: ");
  });
});
