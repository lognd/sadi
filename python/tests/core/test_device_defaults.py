"""Device service defaults that must hold on slow CI runners."""

from sadi.core import device as dev


# frob:ticket 01M709DXGS91GPWZ3M06FWXJPY
# frob:tests python/sadi/core/device.py::DeviceService.__init__
def test_default_queue_rides_out_a_slow_runner() -> None:
    """The default depth absorbs a macOS-runner fsync stall (about 0.3 s at ~1000 blocks/s)."""
    assert dev.DEFAULT_QUEUE_BLOCKS >= 4096
