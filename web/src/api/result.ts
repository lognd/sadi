/** Result type mirroring typani on the backend: fallible calls return values, not throws. */
export type Result<T, E> = { ok: true; value: T } | { ok: false; error: E };

/** Wrap a success value. */
export const ok = <T>(value: T): Result<T, never> => ({ ok: true, value });

/** Wrap a failure. */
export const err = <E>(error: E): Result<never, E> => ({ ok: false, error });
