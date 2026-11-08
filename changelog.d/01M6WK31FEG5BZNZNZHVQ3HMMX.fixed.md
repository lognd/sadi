The server now takes the data-root lock at startup, holds it for its lifetime and refuses to start (RootLockFailed) when it is held or stale.
