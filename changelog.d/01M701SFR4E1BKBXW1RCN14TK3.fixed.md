Data-root stale-lock detection now reads the recorded pid through the locked handle, so a crashed holder is reported on Windows instead of being silently taken over.
