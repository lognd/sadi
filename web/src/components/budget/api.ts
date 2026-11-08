// frob:ticket 01M6W7R432XQSR47M3W61M215J
import { getJson, type ApiError } from "../../api/client";
import type { Result } from "../../api/result";
import type { ResultBudget } from "./types";

/**
 * Fetch per-result budgets (GET /api/results/budgets).
 * The endpoint is owned by ~J73KJ11 and may not exist yet; callers get an http error Result.
 */
export function getBudgets(
  fetchImpl: typeof fetch = fetch,
): Promise<Result<ResultBudget[], ApiError>> {
  return getJson<ResultBudget[]>("/api/results/budgets", fetchImpl);
}
