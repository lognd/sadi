"""Check modules; importing this package registers every check and remedy."""

# frob:ticket 01M6WA9WYE9D71BBA7AV3H5CGF
from sadi.doctor.checks import (
    brw,
    clk,
    data,
    dev,
    ext,
    net,
    plat,
    plg,
    py,
    res,
    sess,
    sim,
    usb,
    wal,
    web,
    wrk,
)

__all__ = [
    "brw",
    "clk",
    "data",
    "dev",
    "ext",
    "net",
    "plat",
    "plg",
    "py",
    "res",
    "sess",
    "sim",
    "usb",
    "wal",
    "web",
    "wrk",
]
