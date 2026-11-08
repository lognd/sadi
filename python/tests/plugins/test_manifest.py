"""Tests for sadi.plugins manifest loading and api_version compatibility."""

# frob:ticket 01M6WFYFTBG9T5MNPJJC0E4R63

from __future__ import annotations

from pathlib import Path

from typani import Err, Ok

from sadi.plugins import (
    PLUGIN_API_VERSION,
    PluginApiVersionError,
    PluginManifest,
    PluginManifestError,
    check_api_compat,
    load_manifest_toml,
)

GOOD = """
id = "lctt"
version = "1.2.0"
api_version = ">=1.0,<2"

[contributions]
labs = ["sadi.labs.lctt:make_lab"]

[[requires]]
id = "other-plugin"
version = ">=0.3"
"""


def _write(tmp_path: Path, text: str) -> Path:
    """Write manifest text to a temp file and return its path."""
    p = tmp_path / "sadi_plugin.toml"
    p.write_text(text, encoding="utf-8")
    return p


# frob:tests python/sadi/plugins/manifest.py::load_manifest_toml
def test_valid_manifest_round_trips(tmp_path: Path) -> None:
    """A valid TOML file loads into an equal model."""
    r = load_manifest_toml(_write(tmp_path, GOOD))
    assert isinstance(r, Ok)
    m = r.unwrap()
    assert m.id == "lctt"
    assert m.contributions.labs == ("sadi.labs.lctt:make_lab",)
    assert m.contributions.exports == ()
    assert m.requires[0].id == "other-plugin"
    assert PluginManifest.model_validate(m.model_dump()) == m


# frob:tests python/sadi/plugins/manifest.py::load_manifest_toml
def test_missing_file_is_err(tmp_path: Path) -> None:
    """A missing file yields Unreadable."""
    r = load_manifest_toml(tmp_path / "nope.toml")
    assert isinstance(r, Err)
    assert r.unwrap_err() is PluginManifestError.Unreadable


# frob:tests python/sadi/plugins/manifest.py::load_manifest_toml
def test_bad_toml_is_err(tmp_path: Path) -> None:
    """Broken TOML yields BadToml."""
    r = load_manifest_toml(_write(tmp_path, "id = ["))
    assert r.unwrap_err() is PluginManifestError.BadToml


# frob:tests python/sadi/plugins/manifest.py::load_manifest_toml
def test_missing_field_is_err(tmp_path: Path) -> None:
    """A missing required field yields MissingField naming it."""
    r = load_manifest_toml(_write(tmp_path, 'id = "x"\nversion = "1"\n'))
    assert r.unwrap_err() is PluginManifestError.MissingField
    assert any("api_version" in n for n in r.notes)


# frob:tests python/sadi/plugins/manifest.py::load_manifest_toml
def test_invalid_fields_are_err(tmp_path: Path) -> None:
    """Bad slug, version, range, entrypoint and unknown keys yield InvalidField."""
    bad = [
        GOOD.replace('id = "lctt"', 'id = "Bad Id"'),
        GOOD.replace('"1.2.0"', '"not-a-version"'),
        GOOD.replace('">=1.0,<2"', '"banana"'),
        GOOD.replace("sadi.labs.lctt:make_lab", "no_colon"),
        GOOD + "extra = 1\n",
    ]
    for text in bad:
        r = load_manifest_toml(_write(tmp_path, text))
        assert r.unwrap_err() is PluginManifestError.InvalidField, text


# frob:tests python/sadi/plugins/manifest.py::check_api_compat
def test_api_compatible_is_ok(tmp_path: Path) -> None:
    """A range containing the host API version passes."""
    m = load_manifest_toml(_write(tmp_path, GOOD)).unwrap()
    assert isinstance(check_api_compat(m), Ok)


# frob:tests python/sadi/plugins/manifest.py::check_api_compat
def test_api_incompatible_names_both_versions(tmp_path: Path) -> None:
    """An excluding range yields Incompatible whose note names both versions."""
    m = load_manifest_toml(_write(tmp_path, GOOD.replace(">=1.0,<2", ">=2"))).unwrap()
    r = check_api_compat(m)
    assert r.unwrap_err() is PluginApiVersionError.Incompatible
    note = " ".join(r.notes)
    assert ">=2" in note
    assert PLUGIN_API_VERSION in note
