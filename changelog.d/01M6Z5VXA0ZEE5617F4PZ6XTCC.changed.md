Fix flaky AD3 signal subprocess tests: the READY marker is now a raw write so a SIGTERM cannot hit a held stdout buffer lock.
