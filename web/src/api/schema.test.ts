// frob:ticket 01M6WTCA5YQJPPTGFH316XQ2DQ
// frob:accept COV001 because="TypeScript frob:tests does not resolve; the drift test covers generated schema.ts"
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import openapiTS, { astToString } from "openapi-typescript";
import { describe, expect, it } from "vitest";

const here = (name: string): string => fileURLToPath(new URL(name, import.meta.url));

describe("generated API client", () => {
  it("schema.ts is the generator output for the committed openapi.json", async () => {
    const spec = JSON.parse(readFileSync(here("./openapi.json"), "utf-8")) as object;
    const ast = await openapiTS(spec as never);
    const fresh = astToString(ast).trim();
    const committed = readFileSync(here("./schema.ts"), "utf-8").replace(/\r\n/g, "\n");
    expect(committed).toContain(fresh);
  });

  it("covers the core route families", () => {
    const spec = JSON.parse(readFileSync(here("./openapi.json"), "utf-8")) as {
      paths: Record<string, unknown>;
    };
    expect(Object.keys(spec.paths)).toContain("/api/plugins");
  });
});
