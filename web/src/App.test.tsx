// frob:ticket 01M6XAASMZX11EZ5NYC3FNTQ6Z
import { renderToString } from "react-dom/server";
import { describe, expect, test } from "vitest";
import { App } from "./App";

describe("App", () => {
  test("renders the initial connection state", () => {
    expect(renderToString(<App />)).toContain("backend: ");
  });

  test("Doctor button precedes the wizard in DOM (Tab) order inside a labelled nav", () => {
    const html = renderToString(<App />);
    expect(html).toContain('<nav aria-label="Tools">');
    expect(html.indexOf("Doctor")).toBeGreaterThan(-1);
    expect(html.indexOf("Doctor")).toBeLessThan(html.indexOf("backend: "));
  });
});
