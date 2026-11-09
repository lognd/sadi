Fix `inject.capture` reading before acquisition finished on real hardware: it now waits (bounded) for DONE via `wait_acquired`.
