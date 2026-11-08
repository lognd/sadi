"""Byte-level tests for the CSV export eol policy: CRLF, UTF-8, no overwrite."""

# frob:ticket 01M6WA538CKP1CX6Q11K79AJH0
from __future__ import annotations

from pathlib import Path

from sadi.store.csv_export import UTF8_BOM, render_csv, write_csv_exclusive

_HEADER = ["t_s", "unit", "note"]
_ROWS = [[0.5, "µm", "a,b"], [1, "N", 'line1\nline2 "q"']]
_EXPECTED = b't_s,unit,note\r\n0.5,\xc2\xb5m,"a,b"\r\n1,N,"line1\nline2 ""q"""\r\n'


# frob:tests python/sadi/store/csv_export.py::render_csv
def test_render_bytes_exact_crlf() -> None:
    """Every row ends in CRLF; embedded newlines are left untouched; UTF-8 encoded."""
    assert render_csv(_HEADER, _ROWS) == _EXPECTED


# frob:tests python/sadi/store/csv_export.py::render_csv
def test_render_excel_bom() -> None:
    """The optional BOM is exactly the three UTF-8 BOM bytes in front."""
    assert render_csv(_HEADER, _ROWS, excel_bom=True) == UTF8_BOM + _EXPECTED


# frob:tests python/sadi/store/csv_export.py::write_csv_exclusive
def test_file_bytes_match_render(tmp_path: Path) -> None:
    """The file on disk holds exactly the rendered bytes (no newline translation)."""
    dst = tmp_path / "out.csv"
    result = write_csv_exclusive(dst, _HEADER, _ROWS)
    assert result.is_ok
    assert result.unwrap() == len(_EXPECTED)
    assert dst.read_bytes() == _EXPECTED


# frob:tests python/sadi/store/csv_export.py::write_csv_exclusive
def test_never_overwrites(tmp_path: Path) -> None:
    """An existing file yields Err and keeps its original bytes."""
    dst = tmp_path / "out.csv"
    dst.write_bytes(b"precious")
    result = write_csv_exclusive(dst, _HEADER, _ROWS)
    assert result.is_err
    assert dst.read_bytes() == b"precious"


# frob:tests python/sadi/store/csv_export.py::write_csv_exclusive
def test_gitattributes_pins_csv_bytes() -> None:
    """The repo .gitattributes declares CSV as -text and JSON as eol=lf."""
    root = Path(__file__).resolve().parents[3]
    lines = (root / ".gitattributes").read_text(encoding="ascii").splitlines()
    assert "*.csv -text" in lines
    assert "*.json text eol=lf" in lines
