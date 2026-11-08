/* Stub until B4 (FastAPI app) exists; `npm run gen:api` overwrites this file. */

export interface paths {
  "/api/health": {
    get: { responses: { 200: { content: { "application/json": components["schemas"]["Health"] } } } };
  };
}

export interface components {
  schemas: {
    Health: { status: string; version: string };
  };
}
