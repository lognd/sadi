A failed writer now spills its unsaved records to a recoverable spill file on close and shutdown instead of dropping them; if no spill location works, close returns 409 and keeps them in memory.
