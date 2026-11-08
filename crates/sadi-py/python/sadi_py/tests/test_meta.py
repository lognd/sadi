"""Tests for sadi_py build metadata and the built-in self-test."""

import sadi_py as sp


def test_version_and_protocol() -> None:
    assert isinstance(sp.__version__, str) and sp.__version__
    assert isinstance(sp.PROTOCOL_VERSION, int)


# frob:tests crates/sadi-py/python/sadi_py/__init__.pyi::serial_features
def test_serial_features_are_names() -> None:
    feats = sp.serial_features()
    assert all(isinstance(f, str) for f in feats)


# frob:tests crates/sadi-py/python/sadi_py/__init__.pyi::selftest
def test_selftest_passes() -> None:
    sp.selftest()
