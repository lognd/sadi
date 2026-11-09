"""Real SADI packet framing produced by the AD3 LCTT source."""

# frob:ticket 01M6Z3FR114SYB4SDYQVQPGZXY
from __future__ import annotations

import numpy as np
import pytest

from sadi.bench.lctt_source import Ad3Source
from tests.e2e.ad3_flow import make_fake


# frob:tests python/sadi/bench/lctt_source.py::Ad3Source.to_block
def test_to_block_emits_real_sadi_packets() -> None:
    """Each 612-byte frame has sync, type 5, running state, LE msg_count, BE codes and tail."""
    be = make_fake()
    dev = be.open(0).danger_ok
    src = Ad3Source(be, dev)
    try:
        vols = np.zeros((60, 4))
        vols[:, 0] = 0.25
        a = src.to_block(vols)
        b = src.to_block(vols)
        with pytest.raises(ValueError):
            src.to_block(vols, 600)
    finally:
        src.stop()
        be.close(dev)
    assert len(a.raw) == 2 * 612
    for k in range(2):
        f = a.raw[k * 612 : (k + 1) * 612]
        assert f[0] == 0x55 and f[1] == 5 and f[2] == 3
        assert int.from_bytes(f[4:8], "little") == k
        assert f[608:] == bytes([0xAA, 0x55, 0xAA, 0x55])
    assert int.from_bytes(a.raw[12:14], "big") == src.adc.quantise(0.25)
    assert int.from_bytes(b.raw[4:8], "little") == 2
    assert int(b.msg_count[0]) == 2
