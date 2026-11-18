"""RunOptions.probe_device=False never touches the board (audit1 #11)."""

# frob:ticket 01M71XGJ7JM6YWRWCPMTRQJ0A5
from __future__ import annotations

from doctor_fakes import healthy

import sadi.doctor as doctor
from sadi.doctor.schema import Layer, RunOptions, SkipReason, Status


# frob:tests python/sadi/doctor/__init__.py::run
def test_no_probe_skips_dev_layer_without_calling_device_facts() -> None:
    p = healthy()

    def boom(*_a: object) -> None:
        raise AssertionError("device probed")

    p.device_facts = boom  # type: ignore[method-assign]
    rep = doctor.run(RunOptions(layers=(Layer.DEV,), probe_device=False), p).unwrap()
    assert rep.results
    assert any(r.skip_reason is SkipReason.READ_ONLY for r in rep.results)
    assert all(
        r.status is Status.SKIP and r.skip_reason in {SkipReason.READ_ONLY, SkipReason.OPT_IN}
        for r in rep.results
    )
