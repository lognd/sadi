Fix Windows lock handling: lock a byte past the data so lock files stay readable, decode MoveFileExW errors, and check process exit code in pid_alive.
