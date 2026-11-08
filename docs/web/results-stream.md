# Results stream client

Status: current

Parent: [plots.md](plots.md), [../server/results-stream.md](../server/results-stream.md). Code:
`web/src/results-stream/` (ticket ~4XEGRNJ).

Client for the versioned `ResultEnvelope` stream. Transport-agnostic: a `Subscribe` function
delivers raw JSON texts (snake_case wire form, `protocol_version` 1).

- `parseEnvelope` validates one envelope without throwing (`EnvelopeError` on failure).
- `applyEnvelope` keeps the latest envelope per key and the newest `data_version` seen; envelopes
  whose `result_version` is not newer for their key are dropped.
- `isStale`: server state `stale`, or `data_version` below the newest seen. `isRefining`: state
  `refining` and not stale.
- `connectResults(subscribe, onState)` and the hook `useResultsStream(subscribe)` (subscribe must
  be referentially stable) expose the `StreamState`.
- `StreamedValue` renders a key with a "(stale)" marker whenever the value lags, and a progress
  bar (0..100) while MC/GP refine. A value is never shown older than the newest data without the
  marker. Malformed envelopes are logged and ignored.
- `wsSubscribe(opts)` (`wsSubscribe.ts`) is the production `Subscribe`: each subscription opens a
  reconnecting `ws/client.ts` `openStream` on `WS /api/stream`, forwards only RESULTS_ENVELOPE frame
  bodies (see [../server/websocket.md](../server/websocket.md)) and ignores trace frames; undecodable
  input is logged. After a reconnect the server may replay envelopes: `applyEnvelope` drops any whose
  `result_version` is not newer, so state never regresses. Unsubscribing closes the socket and cancels
  pending reconnects. `onConn` taps the `ConnState`. Build it once (stable reference) for the hook.
