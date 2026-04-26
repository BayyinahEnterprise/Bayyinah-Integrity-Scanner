"""
Tests for analyzers.csv_analyzer.CsvAnalyzer.

Phase 20 guardrails. CsvAnalyzer is a dual witness — zahir (formula
injection that renders in a spreadsheet app, per-cell Unicode
concealment) and batin (null bytes, BOM anomalies, mixed encoding,
mixed delimiters, comment rows, inconsistent columns, unbalanced
quotes, and oversized DoS-shaped fields). Each detector has a
targeted unit test that builds minimal CSV bytes in ``tmp_path`` and
scans it in isolation.

The builders here are intentionally separate from
``tests/make_csv_fixtures.py``. That module produces the committed
fixture corpus; these tests build one-off bytes per test so each
detector can be exercised in isolation with clean pass/fail semantics
(including the 1 MiB ``csv_oversized_field`` case, which would be
heavy to ship as a committed fixture).

Mirrors the structure of ``tests/analyzers/test_eml_analyzer.py`` and
``tests/analyzers/test_pptx_analyzer.py``.

Al-Baqarah 2:42: "Do not mix truth with falsehood, nor conceal the
truth while you know it." Each per-detector test is a single
pretend-truth / real-truth pair — the analyzer's job is to surface
the second when the first is performed.
"""

from __future__ import annotations

from pathlib import Path

from analyzers import CsvAnalyzer
from analyzers.base import BaseAnalyzer
from analyzers.csv_analyzer import _column_ref
from domain import IntegrityReport
from infrastructure.file_router import FileKind


# ---------------------------------------------------------------------------
# Contract
# ---------------------------------------------------------------------------


def test_is_base_analyzer_subclass() -> None:
    assert issubclass(CsvAnalyzer, BaseAnalyzer)


def test_class_attributes() -> None:
    assert CsvAnalyzer.name == "csv"
    assert CsvAnalyzer.error_prefix == "CSV scan error"
    # Class-level source_layer is batin for ``scan_error`` attribution.
    # Per-finding source_layer is set explicitly on every zahir detector.
    assert CsvAnalyzer.source_layer == "batin"


def test_supported_kinds_is_csv_only() -> None:
    assert CsvAnalyzer.supported_kinds == frozenset({FileKind.CSV})


# ---------------------------------------------------------------------------
# Byte-construction helpers
# ---------------------------------------------------------------------------

CRLF = b"\r\n"


def _csv_bytes(*lines: str | bytes) -> bytes:
    out: list[bytes] = []
    for line in lines:
        if isinstance(line, str):
            out.append(line.encode("utf-8"))
        else:
            out.append(line)
    return CRLF.join(out) + CRLF


def _write(tmp_path: Path, name: str, data: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


def _mechanisms(report: IntegrityReport) -> set[str]:
    return {f.mechanism for f in report.findings}


# ---------------------------------------------------------------------------
# Clean — nothing fires
# ---------------------------------------------------------------------------


def test_clean_comma_scores_1(tmp_path: Path) -> None:
    data = _csv_bytes(
        "name,age,city",
        "Alice,30,Seattle",
        "Bob,25,Boston",
    )
    path = _write(tmp_path, "clean.csv", data)
    report = CsvAnalyzer().scan(path)
    assert report.findings == []
    assert report.integrity_score == 1.0
    assert not report.scan_incomplete


def test_clean_tab_scores_1(tmp_path: Path) -> None:
    data = _csv_bytes(
        "name\tage\tcity",
        "Alice\t30\tSeattle",
        "Bob\t25\tBoston",
    )
    path = _write(tmp_path, "clean.tsv", data)
    report = CsvAnalyzer().scan(path)
    assert report.findings == []
    assert report.integrity_score == 1.0


def test_clean_pipe_scores_1(tmp_path: Path) -> None:
    data = _csv_bytes(
        "name|age|city",
        "Alice|30|Seattle",
        "Bob|25|Boston",
    )
    path = _write(tmp_path, "clean.psv", data)
    report = CsvAnalyzer().scan(path)
    assert report.findings == []
    assert report.integrity_score == 1.0


# ---------------------------------------------------------------------------
# Zahir — formula injection (one test per OWASP prefix char)
# ---------------------------------------------------------------------------


def test_formula_injection_equals_fires(tmp_path: Path) -> None:
    data = _csv_bytes("h1,h2,h3", "a,b,=1+1", "c,d,e")
    path = _write(tmp_path, "eq.csv", data)
    report = CsvAnalyzer().scan(path)
    assert "csv_formula_injection" in _mechanisms(report)


def test_formula_injection_plus_fires(tmp_path: Path) -> None:
    data = _csv_bytes("h1,h2,h3", "a,b,+1+1", "c,d,e")
    path = _write(tmp_path, "plus.csv", data)
    report = CsvAnalyzer().scan(path)
    assert "csv_formula_injection" in _mechanisms(report)


def test_formula_injection_minus_fires(tmp_path: Path) -> None:
    data = _csv_bytes("h1,h2,h3", "a,b,-2+3", "c,d,e")
    path = _write(tmp_path, "minus.csv", data)
    report = CsvAnalyzer().scan(path)
    assert "csv_formula_injection" in _mechanisms(report)


def test_formula_injection_at_fires(tmp_path: Path) -> None:
    data = _csv_bytes("h1,h2,h3", "a,b,@SUM(1+1)", "c,d,e")
    path = _write(tmp_path, "at.csv", data)
    report = CsvAnalyzer().scan(path)
    assert "csv_formula_injection" in _mechanisms(report)


def test_formula_injection_tab_fires(tmp_path: Path) -> None:
    # Quoted cell whose first codepoint is TAB.
    data = _csv_bytes("h1,h2,h3", "a,\"\tformula\",c", "d,e,f")
    path = _write(tmp_path, "tab.csv", data)
    report = CsvAnalyzer().scan(path)
    assert "csv_formula_injection" in _mechanisms(report)


def test_formula_injection_cr_fires(tmp_path: Path) -> None:
    """Leading carriage return inside a quoted cell is a formula trigger
    in some clipboard paths. Covered as a unit test rather than a
    committed fixture because the raw CR interacts with ``splitlines``
    in a way that bloats a committed fixture's expectation set —
    ``splitlines`` splits on CR, so the quoting check reads each half
    of the split line separately and emits a quoting-anomaly finding
    alongside the formula finding. Both firings are correct; the
    single-responsibility fixture corpus prefers to isolate the
    formula-injection signal in the TAB fixture instead, and let this
    unit test carry the CR case.
    """
    data = _csv_bytes("h1,h2,h3", "a,\"\rformula\",c", "d,e,f")
    path = _write(tmp_path, "cr.csv", data)
    report = CsvAnalyzer().scan(path)
    assert "csv_formula_injection" in _mechanisms(report)


def test_formula_injection_ignores_non_leading_formula_chars(
    tmp_path: Path,
) -> None:
    """A ``=`` mid-cell is not a formula prefix; only ``cell[0]`` counts."""
    data = _csv_bytes("h1,h2,h3", "a,b,foo=1+1", "c,d,e")
    path = _write(tmp_path, "midcell.csv", data)
    report = CsvAnalyzer().scan(path)
    assert "csv_formula_injection" not in _mechanisms(report)


def test_formula_injection_fires_once_per_offending_cell(
    tmp_path: Path,
) -> None:
    data = _csv_bytes(
        "h1,h2,h3",
        "=A1,=B1,=C1",
        "a,b,c",
    )
    path = _write(tmp_path, "triple.csv", data)
    report = CsvAnalyzer().scan(path)
    formula_findings = [
        f for f in report.findings if f.mechanism == "csv_formula_injection"
    ]
    assert len(formula_findings) == 3


def test_formula_injection_is_zahir_layer(tmp_path: Path) -> None:
    data = _csv_bytes("h1,h2,h3", "a,b,=1+1", "c,d,e")
    path = _write(tmp_path, "zahir.csv", data)
    report = CsvAnalyzer().scan(path)
    [f] = [
        f for f in report.findings if f.mechanism == "csv_formula_injection"
    ]
    assert f.source_layer == "zahir"


# ---------------------------------------------------------------------------
# Batin — null byte
# ---------------------------------------------------------------------------


def test_null_byte_fires(tmp_path: Path) -> None:
    data = b"h1,h2,h3\r\nalpha,null\x00byte,gamma\r\n"
    path = _write(tmp_path, "nul.csv", data)
    report = CsvAnalyzer().scan(path)
    assert "csv_null_byte" in _mechanisms(report)


def test_null_byte_does_not_fire_scan_error(tmp_path: Path) -> None:
    """The NUL-sanitisation path in ``scan()`` must prevent
    ``csv.reader`` from raising ``line contains NUL`` — no scan_error,
    no scan_incomplete clamp.
    """
    data = b"h1,h2,h3\r\nalpha,null\x00byte,gamma\r\n"
    path = _write(tmp_path, "nul.csv", data)
    report = CsvAnalyzer().scan(path)
    assert "scan_error" not in _mechanisms(report)
    assert not report.scan_incomplete
    assert report.error is None


def test_null_byte_absent_does_not_fire(tmp_path: Path) -> None:
    data = _csv_bytes("h1,h2,h3", "a,b,c")
    path = _write(tmp_path, "clean.csv", data)
    report = CsvAnalyzer().scan(path)
    assert "csv_null_byte" not in _mechanisms(report)


# ---------------------------------------------------------------------------
# Batin — BOM anomaly
# ---------------------------------------------------------------------------


def test_bom_leading_fires(tmp_path: Path) -> None:
    data = b"\xef\xbb\xbf" + _csv_bytes("h1,h2", "a,b")
    path = _write(tmp_path, "bom_lead.csv", data)
    report = CsvAnalyzer().scan(path)
    assert "csv_bom_anomaly" in _mechanisms(report)


def test_bom_leading_does_not_carry_into_header_cell(
    tmp_path: Path,
) -> None:
    """Leading BOM is stripped before the row walk — no downstream
    ``zero_width_chars`` finding on the first header cell."""
    data = b"\xef\xbb\xbf" + _csv_bytes("h1,h2", "a,b")
    path = _write(tmp_path, "bom_lead.csv", data)
    report = CsvAnalyzer().scan(path)
    assert "zero_width_chars" not in _mechanisms(report)


def test_bom_embedded_fires(tmp_path: Path) -> None:
    data = b"h1,h2\r\n" + b"\xef\xbb\xbf" + b"alpha,beta\r\n"
    path = _write(tmp_path, "bom_mid.csv", data)
    report = CsvAnalyzer().scan(path)
    assert "csv_bom_anomaly" in _mechanisms(report)


def test_bom_double_fires_twice(tmp_path: Path) -> None:
    """Leading BOM + a second mid-stream BOM emits two findings."""
    data = b"\xef\xbb\xbfh1,h2\r\n" + b"\xef\xbb\xbfalpha,beta\r\n"
    path = _write(tmp_path, "bom_double.csv", data)
    report = CsvAnalyzer().scan(path)
    bom_findings = [
        f for f in report.findings if f.mechanism == "csv_bom_anomaly"
    ]
    assert len(bom_findings) == 2


def test_bom_absent_does_not_fire(tmp_path: Path) -> None:
    data = _csv_bytes("h1,h2", "a,b")
    path = _write(tmp_path, "clean.csv", data)
    report = CsvAnalyzer().scan(path)
    assert "csv_bom_anomaly" not in _mechanisms(report)


# ---------------------------------------------------------------------------
# Batin — mixed encoding
# ---------------------------------------------------------------------------


def test_mixed_encoding_fires(tmp_path: Path) -> None:
    # Lone 0xFF is never valid UTF-8 but always valid Latin-1.
    data = b"h1,h2\r\ntest\xffdata,value\r\n"
    path = _write(tmp_path, "latin.csv", data)
    report = CsvAnalyzer().scan(path)
    assert "csv_mixed_encoding" in _mechanisms(report)


def test_mixed_encoding_utf8_clean_silent(tmp_path: Path) -> None:
    data = "h1,h2\r\nnaïve,café\r\n".encode("utf-8")
    path = _write(tmp_path, "utf8_ok.csv", data)
    report = CsvAnalyzer().scan(path)
    assert "csv_mixed_encoding" not in _mechanisms(report)


# ---------------------------------------------------------------------------
# Batin — mixed delimiter
# ---------------------------------------------------------------------------


def test_mixed_delimiter_fires(tmp_path: Path) -> None:
    data = _csv_bytes(
        "A,B\tC,D\tE,F\tG",
        "1,2\t3,4\t5,6\t7",
        "a,b\tc,d\te,f\tg",
        "x,y\tz,w\tu,v\tq",
    )
    path = _write(tmp_path, "mixed_delim.csv", data)
    report = CsvAnalyzer().scan(path)
    assert "csv_mixed_delimiter" in _mechanisms(report)


def test_single_delimiter_silent(tmp_path: Path) -> None:
    data = _csv_bytes("a,b,c", "1,2,3", "4,5,6")
    path = _write(tmp_path, "pure_comma.csv", data)
    report = CsvAnalyzer().scan(path)
    assert "csv_mixed_delimiter" not in _mechanisms(report)


# ---------------------------------------------------------------------------
# Batin — comment row
# ---------------------------------------------------------------------------


def test_comment_row_fires(tmp_path: Path) -> None:
    data = _csv_bytes(
        "# generated by export_pipeline v3",
        "name,age",
        "Alice,30",
    )
    path = _write(tmp_path, "comment.csv", data)
    report = CsvAnalyzer().scan(path)
    assert "csv_comment_row" in _mechanisms(report)


def test_comment_row_does_not_cause_inconsistent_columns(
    tmp_path: Path,
) -> None:
    data = _csv_bytes(
        "# comment",
        "name,age",
        "Alice,30",
        "Bob,25",
    )
    path = _write(tmp_path, "comment_cols.csv", data)
    report = CsvAnalyzer().scan(path)
    assert "csv_inconsistent_columns" not in _mechanisms(report)


def test_comment_row_absent_silent(tmp_path: Path) -> None:
    data = _csv_bytes("name,age", "Alice,30")
    path = _write(tmp_path, "no_comment.csv", data)
    report = CsvAnalyzer().scan(path)
    assert "csv_comment_row" not in _mechanisms(report)


# ---------------------------------------------------------------------------
# Batin — inconsistent column count
# ---------------------------------------------------------------------------


def test_inconsistent_columns_fires(tmp_path: Path) -> None:
    data = _csv_bytes("h1,h2,h3", "a,b,c", "d,e,f,extra")
    path = _write(tmp_path, "ragged.csv", data)
    report = CsvAnalyzer().scan(path)
    assert "csv_inconsistent_columns" in _mechanisms(report)


def test_consistent_columns_silent(tmp_path: Path) -> None:
    data = _csv_bytes("h1,h2,h3", "a,b,c", "d,e,f")
    path = _write(tmp_path, "ok.csv", data)
    report = CsvAnalyzer().scan(path)
    assert "csv_inconsistent_columns" not in _mechanisms(report)


# ---------------------------------------------------------------------------
# Batin — quoting anomaly
# ---------------------------------------------------------------------------


def test_quoting_anomaly_fires(tmp_path: Path) -> None:
    # Last line has an odd unescaped quote count and is at EOF with no
    # trailing terminator, so csv.reader tolerates the unclosed quote.
    data = b"h1,h2,h3\r\nalpha,beta,gamma\r\nd,e,\"unclosed"
    path = _write(tmp_path, "bad_quote.csv", data)
    report = CsvAnalyzer().scan(path)
    assert "csv_quoting_anomaly" in _mechanisms(report)


def test_escaped_double_quote_silent(tmp_path: Path) -> None:
    """A canonical ``""`` inside a quoted cell is balanced — no anomaly."""
    data = _csv_bytes("h1,h2,h3", "\"a\"\"b\",\"c\",\"d\"")
    path = _write(tmp_path, "escaped.csv", data)
    report = CsvAnalyzer().scan(path)
    assert "csv_quoting_anomaly" not in _mechanisms(report)


# ---------------------------------------------------------------------------
# Batin — oversized field (DoS)
# ---------------------------------------------------------------------------


def test_oversized_field_fires(tmp_path: Path) -> None:
    """A cell at or above the 1 MiB threshold fires the DoS detector.

    Kept as a unit test rather than a committed fixture so the repo
    doesn't carry a megabyte-scale CSV. Relies on the module-load
    ``csv.field_size_limit`` adjustment so csv.reader doesn't raise
    its default 128 KiB limit before the detector runs.
    """
    huge = b"A" * (1024 * 1024)  # exactly threshold — 1 MiB
    data = b"h1,h2,h3\r\nalpha," + huge + b",gamma\r\n"
    path = _write(tmp_path, "dos.csv", data)
    report = CsvAnalyzer().scan(path)
    assert "csv_oversized_field" in _mechanisms(report)
    assert "scan_error" not in _mechanisms(report)
    assert not report.scan_incomplete


def test_normal_sized_field_silent(tmp_path: Path) -> None:
    modest = "x" * 1000
    data = _csv_bytes("h1,h2,h3", f"alpha,{modest},gamma")
    path = _write(tmp_path, "modest.csv", data)
    report = CsvAnalyzer().scan(path)
    assert "csv_oversized_field" not in _mechanisms(report)


# ---------------------------------------------------------------------------
# Zahir — per-cell Unicode concealment (shared mechanism names)
# ---------------------------------------------------------------------------


def test_zero_width_in_cell_fires(tmp_path: Path) -> None:
    data = _csv_bytes("label,note", "entry,bad\u200Bvalue")
    path = _write(tmp_path, "zw.csv", data)
    report = CsvAnalyzer().scan(path)
    assert "zero_width_chars" in _mechanisms(report)


def test_tag_chars_in_cell_fires(tmp_path: Path) -> None:
    # U+E0049 + U+E004F — TAG LATIN CAPITAL I and O.
    data = _csv_bytes(
        "label,note",
        "entry,plain\U000E0049\U000E004Fsuffix",
    )
    path = _write(tmp_path, "tags.csv", data)
    report = CsvAnalyzer().scan(path)
    assert "tag_chars" in _mechanisms(report)


def test_bidi_in_cell_fires(tmp_path: Path) -> None:
    data = _csv_bytes("label,note", "entry,invoice\u202Efdp.doc")
    path = _write(tmp_path, "bidi.csv", data)
    report = CsvAnalyzer().scan(path)
    assert "bidi_control" in _mechanisms(report)


def test_homoglyph_in_cell_fires(tmp_path: Path) -> None:
    # U+0430 (Cyrillic a) + Latin pple.
    data = _csv_bytes("label,note", "entry,\u0430pple")
    path = _write(tmp_path, "homo.csv", data)
    report = CsvAnalyzer().scan(path)
    assert "homoglyph" in _mechanisms(report)


def test_clean_ascii_cell_silent(tmp_path: Path) -> None:
    data = _csv_bytes("label,note", "entry,apple")
    path = _write(tmp_path, "plain.csv", data)
    report = CsvAnalyzer().scan(path)
    for m in ("zero_width_chars", "tag_chars", "bidi_control", "homoglyph"):
        assert m not in _mechanisms(report)


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_missing_file_surfaces_scan_error(tmp_path: Path) -> None:
    report = CsvAnalyzer().scan(tmp_path / "no-such-file.csv")
    mechs = _mechanisms(report)
    # The base-class helper wraps OSError/IOError as a single scan_error
    # finding; the scan is then marked incomplete.
    assert "scan_error" in mechs
    assert report.scan_incomplete


def test_empty_file_does_not_crash(tmp_path: Path) -> None:
    path = _write(tmp_path, "empty.csv", b"")
    report = CsvAnalyzer().scan(path)
    # Empty file: no findings, score 1.0, not incomplete.
    assert report.findings == []
    assert report.integrity_score == 1.0
    assert not report.scan_incomplete


# ---------------------------------------------------------------------------
# Internal helper — _column_ref
# ---------------------------------------------------------------------------


def test_column_ref_first_letters() -> None:
    assert _column_ref(0) == "A"
    assert _column_ref(1) == "B"
    assert _column_ref(25) == "Z"


def test_column_ref_two_letter_wraparound() -> None:
    assert _column_ref(26) == "AA"
    assert _column_ref(27) == "AB"
    assert _column_ref(51) == "AZ"
    assert _column_ref(52) == "BA"


def test_column_ref_negative_returns_placeholder() -> None:
    assert _column_ref(-1) == "?"
