"""Check modules; importing this package registers every check and remedy."""

# frob:ticket 01M6WA9WYE9D71BBA7AV3H5CGF
from sadi.doctor.checks import brw, clk, data, ext, net, plat, plg, py, res, sess, usb, wal, web

__all__ = [
    "brw",
    "clk",
    "data",
    "ext",
    "net",
    "plat",
    "plg",
    "py",
    "res",
    "sess",
    "usb",
    "wal",
    "web",
]
