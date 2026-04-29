"""
Tests for the v1.1.2 F2 CSV payload-extraction mechanisms.

These tests exercise the F2 closure: surplus-column payload, column
type drift, quoted-newline payload, bidi codepoints, zero-width
codepoints, and encoding divergence. Each new mechanism gets four
paired tests: catches, recovers payload, clean control, silent on
legitimate edge case.

Each test builds minimal CSV bytes in ``tmp_path`` and scans them in
isolation. The pattern mirrors ``tests/analyzers/test_csv_analyzer.py``
helpers (`_csv_bytes`, `_write`, `_mechanisms`).

Tier 1/2/3 discipline applies: the recovered payload must appear in
the finding's ``concealed`` field, never inferred from the
``surface``.
"""

from __future__ import annotations

from pathlib import Path

from analyzers import CsvAnalyzer
from domain import IntegrityReport


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


def _findings(report: IntegrityReport, mechanism: str):
    return [f for f in report.findings if f.mechanism == mechanism]


def _mechanisms(report: IntegrityReport) -> set[str]:
    return {f.mechanism for f in report.findings}


# ---------------------------------------------------------------------------
# csv_surplus_column_payload (extends csv_inconsistent_columns)
# ---------------------------------------------------------------------------


def test_surplus_column_payload_catches(tmp_path: Path) -> None:
    """Row with extra cells beyond the header fires inconsistent_columns."""
    data = _csv_bytes(
        "description,amount_usd",
        '"clean row",1000',
        '"second invoice",2000,"HIDDEN_TEXT_PAYLOAD: actual revenue $10,000 - see annex"',
    )
    path = _write(tmp_path, "surplus.csv", data)
    report = CsvAnalyzer().scan(path)
    assert "csv_inconsistent_columns" in _mechanisms(report)


def test_surplus_column_payload_recovers_payload(tmp_path: Path) -> None:
    """Recovered payload appears in finding.concealed for surplus cells."""
    data = _csv_bytes(
        "description,amount_usd",
        '"clean row",1000',
        '"second invoice",2000,"HIDDEN_TEXT_PAYLOAD: actual revenue $10,000 - see annex"',
    )
    path = _write(tmp_path, "surplus_recover.csv", data)
    report = CsvAnalyzer().scan(path)
    findings = _findings(report, "csv_inconsistent_columns")
    assert findings, "expected at least one csv_inconsistent_columns finding"
    concealed_text = " ".join(f.concealed for f in findings)
    assert "HIDDEN_TEXT_PAYLOAD" in concealed_text, (
        f"payload not recovered into concealed; got: {concealed_text!r}"
    )
    assert "10,000" in concealed_text, (
        f"$10,000 marker not recovered into concealed; got: {concealed_text!r}"
    )
    assert "Surplus cell content" in concealed_text, (
        f"surplus-cell label missing from concealed; got: {concealed_text!r}"
    )


def test_surplus_column_payload_clean_control(tmp_path: Path) -> None:
    """A consistent CSV emits no csv_inconsistent_columns finding."""
    data = _csv_bytes(
        "description,amount_usd",
        '"clean row one",1000',
        '"clean row two",2000',
    )
    path = _write(tmp_path, "clean.csv", data)
    report = CsvAnalyzer().scan(path)
    assert "csv_inconsistent_columns" not in _mechanisms(report)


def test_surplus_column_payload_silent_on_short_row(tmp_path: Path) -> None:
    """A row with FEWER cells than the header still fires the existing
    detector, but the concealed payload-extraction path stays empty
    (only surplus cells are extracted; missing cells carry no payload).
    """
    data = _csv_bytes(
        "description,amount_usd,note",
        '"first",1000,"clean"',
        '"second",2000',  # short row: 2 cells vs 3-column header
    )
    path = _write(tmp_path, "short.csv", data)
    report = CsvAnalyzer().scan(path)
    findings = _findings(report, "csv_inconsistent_columns")
    assert findings, "expected csv_inconsistent_columns to fire on ragged row"
    concealed_text = " ".join(f.concealed for f in findings)
    # Short row has no surplus cells, so the surplus-cell-content label
    # must not appear.
    assert "Surplus cell content" not in concealed_text, (
        f"surplus-cell label should not appear for short rows; "
        f"got: {concealed_text!r}"
    )


# ---------------------------------------------------------------------------
# csv_column_type_drift (new mechanism)
# ---------------------------------------------------------------------------


_DRIFT_PAYLOAD = (
    "HIDDEN_TEXT_PAYLOAD: actual revenue $10,000 - see annex. "
    "This entire cell is a natural-language paragraph smuggled into a "
    "numeric column. A spreadsheet renders it as the cell contents. "
    "Downstream type-aware consumers see a contract violation against "
    "the column's inferred type signature, but the surface tabular "
    "grid still shows a row with two cells."
)


def test_column_type_drift_catches(tmp_path: Path) -> None:
    """Numeric column carrying a 200+ char free-text payload fires."""
    data = _csv_bytes(
        "sku,amount_usd",
        "A001,1000",
        "A002,2000",
        "A003,3000",
        "A004,4000",
        "A005,5000",
        f'A006,"{_DRIFT_PAYLOAD}"',
    )
    path = _write(tmp_path, "type_drift.csv", data)
    report = CsvAnalyzer().scan(path)
    assert "csv_column_type_drift" in _mechanisms(report)


def test_column_type_drift_recovers_payload(tmp_path: Path) -> None:
    """Recovered payload appears in finding.concealed."""
    data = _csv_bytes(
        "sku,amount_usd",
        "A001,1000",
        "A002,2000",
        "A003,3000",
        "A004,4000",
        "A005,5000",
        f'A006,"{_DRIFT_PAYLOAD}"',
    )
    path = _write(tmp_path, "type_drift_recover.csv", data)
    report = CsvAnalyzer().scan(path)
    findings = _findings(report, "csv_column_type_drift")
    assert findings, "expected at least one csv_column_type_drift finding"
    concealed_text = " ".join(f.concealed for f in findings)
    assert "HIDDEN_TEXT_PAYLOAD" in concealed_text, (
        f"payload not recovered into concealed; got: {concealed_text!r}"
    )
    assert "10,000" in concealed_text, (
        f"$10,000 marker not recovered into concealed; got: {concealed_text!r}"
    )


def test_column_type_drift_clean_control(tmp_path: Path) -> None:
    """A consistent numeric column emits no drift finding."""
    data = _csv_bytes(
        "sku,amount_usd",
        "A001,1000",
        "A002,2000",
        "A003,3000",
        "A004,4000",
        "A005,5000",
        "A006,6000",
    )
    path = _write(tmp_path, "clean_numeric.csv", data)
    report = CsvAnalyzer().scan(path)
    assert "csv_column_type_drift" not in _mechanisms(report)


def test_column_type_drift_silent_on_legitimate_notes_column(
    tmp_path: Path,
) -> None:
    """A column whose header contains 'note' is allowed to carry long
    prose without firing the drift detector. The threshold is
    structural-divergence shaped: long free text in a numeric column
    is a payload; long free text in a notes column is a notes column.
    """
    long_legit_note = (
        "This invoice covers the Q3 milestone delivery for the "
        "customer's onboarding workflow. The amount reflects the "
        "agreed schedule reconciled with the change-order log. "
        "Payment terms are net-30 from the invoice date."
    )
    assert len(long_legit_note) > 200
    data = _csv_bytes(
        "sku,amount_usd,notes",
        "A001,1000,short",
        "A002,2000,short",
        "A003,3000,short",
        "A004,4000,short",
        "A005,5000,short",
        f'A006,6000,"{long_legit_note}"',
    )
    path = _write(tmp_path, "legit_notes.csv", data)
    report = CsvAnalyzer().scan(path)
    assert "csv_column_type_drift" not in _mechanisms(report)


# ---------------------------------------------------------------------------
# csv_quoted_newline_payload (new mechanism)
# ---------------------------------------------------------------------------


_QNL_PAYLOAD = (
    "HIDDEN_TEXT_PAYLOAD: actual revenue $10,000 - see annex.\n"
    "This cell carries multiple paragraphs of natural-language\n"
    "text inside an RFC 4180 quoted region. The grid still shows\n"
    "a single row; the cell content carries the entire payload."
)


def test_quoted_newline_payload_catches(tmp_path: Path) -> None:
    """Quoted cell with 3 embedded newlines and >128 chars fires."""
    data = (
        b"sku,memo\r\n"
        b"A001,\"" + _QNL_PAYLOAD.encode("utf-8") + b"\"\r\n"
    )
    path = _write(tmp_path, "qnl.csv", data)
    report = CsvAnalyzer().scan(path)
    assert "csv_quoted_newline_payload" in _mechanisms(report)


def test_quoted_newline_payload_recovers_payload(tmp_path: Path) -> None:
    """Recovered payload appears in finding.concealed."""
    data = (
        b"sku,memo\r\n"
        b"A001,\"" + _QNL_PAYLOAD.encode("utf-8") + b"\"\r\n"
    )
    path = _write(tmp_path, "qnl_recover.csv", data)
    report = CsvAnalyzer().scan(path)
    findings = _findings(report, "csv_quoted_newline_payload")
    assert findings
    concealed_text = " ".join(f.concealed for f in findings)
    assert "HIDDEN_TEXT_PAYLOAD" in concealed_text, (
        f"payload not recovered into concealed; got: {concealed_text!r}"
    )
    assert "10,000" in concealed_text, (
        f"$10,000 marker not recovered into concealed; got: {concealed_text!r}"
    )


def test_quoted_newline_payload_clean_control(tmp_path: Path) -> None:
    """A clean CSV with no quoted multi-line cells emits no finding."""
    data = _csv_bytes(
        "sku,memo",
        "A001,clean memo",
        "A002,another memo",
    )
    path = _write(tmp_path, "qnl_clean.csv", data)
    report = CsvAnalyzer().scan(path)
    assert "csv_quoted_newline_payload" not in _mechanisms(report)


def test_quoted_newline_payload_silent_on_legitimate_short_address(
    tmp_path: Path,
) -> None:
    """A two-line postal address (1 embedded newline, ~70 chars)
    must NOT fire: the gate requires 2+ newlines AND >128 chars.
    """
    short_address = "123 Main Street\nSpringfield, IL 62704"
    assert short_address.count("\n") == 1
    assert len(short_address) <= 128
    data = (
        b"sku,address\r\n"
        b"A001,\"" + short_address.encode("utf-8") + b"\"\r\n"
    )
    path = _write(tmp_path, "qnl_legit.csv", data)
    report = CsvAnalyzer().scan(path)
    assert "csv_quoted_newline_payload" not in _mechanisms(report)


# ---------------------------------------------------------------------------
# csv_bidi_payload (new mechanism, zahir)
# ---------------------------------------------------------------------------


# Right-to-Left Override (U+202E) inserted before a numeric tail to
# reverse on-screen rendering. The bytes still carry the original.
_RLO = "\u202E"
_LRO = "\u202D"
_PDI = "\u2069"


def test_bidi_payload_catches(tmp_path: Path) -> None:
    """A cell with an RLO codepoint fires csv_bidi_payload."""
    cell_value = f"Total: {_RLO}1000"
    data = _csv_bytes(
        "sku,description",
        f'A001,"{cell_value}"',
    )
    path = _write(tmp_path, "bidi.csv", data)
    report = CsvAnalyzer().scan(path)
    assert "csv_bidi_payload" in _mechanisms(report)


def test_bidi_payload_recovers_payload(tmp_path: Path) -> None:
    """Recovered cell value (with RLO codepoint) appears in concealed."""
    cell_value = f"HIDDEN_TEXT_PAYLOAD: {_RLO}actual revenue $10,000"
    data = _csv_bytes(
        "sku,description",
        f'A001,"{cell_value}"',
    )
    path = _write(tmp_path, "bidi_recover.csv", data)
    report = CsvAnalyzer().scan(path)
    findings = _findings(report, "csv_bidi_payload")
    assert findings
    concealed_text = " ".join(f.concealed for f in findings)
    assert "HIDDEN_TEXT_PAYLOAD" in concealed_text
    assert "10,000" in concealed_text
    # Verify the RLO codepoint is reported in the description.
    desc_text = " ".join(f.description for f in findings)
    assert "U+202E" in desc_text


def test_bidi_payload_clean_control(tmp_path: Path) -> None:
    """A clean ASCII CSV emits no csv_bidi_payload finding."""
    data = _csv_bytes(
        "sku,description",
        "A001,clean text",
        "A002,more clean text",
    )
    path = _write(tmp_path, "bidi_clean.csv", data)
    report = CsvAnalyzer().scan(path)
    assert "csv_bidi_payload" not in _mechanisms(report)


def test_bidi_payload_silent_on_non_bidi_unicode(tmp_path: Path) -> None:
    """A cell with non-bidi Unicode (Arabic, accented Latin) does not
    fire. Only the bidi control codepoints in U+202A..U+202E and
    U+2066..U+2069 trip the detector. Arabic letters are
    right-to-left by intrinsic class, but they are not control
    codepoints; the detector must distinguish.
    """
    data = _csv_bytes(
        "sku,description",
        'A001,"Arabic word: \u0628\u064a\u0651\u0646\u0629"',
        'A002,"Latin accent: caf\u00e9 du jour"',
    )
    path = _write(tmp_path, "bidi_legit.csv", data)
    report = CsvAnalyzer().scan(path)
    assert "csv_bidi_payload" not in _mechanisms(report)


# ---------------------------------------------------------------------------
# csv_zero_width_payload (new mechanism, batin)
# ---------------------------------------------------------------------------


# Zero-width space (U+200B) inserted inside a cell. Renders as no glyph
# in every spreadsheet viewer; the bytes carry the payload.
_ZWSP = "\u200B"
_ZWNJ = "\u200C"
_ZWJ = "\u200D"
_BOM = "\ufeff"


def test_zero_width_payload_catches(tmp_path: Path) -> None:
    """A cell with a U+200B codepoint fires csv_zero_width_payload."""
    cell_value = f"Total: {_ZWSP}1000"
    data = _csv_bytes(
        "sku,description",
        f'A001,"{cell_value}"',
    )
    path = _write(tmp_path, "zw.csv", data)
    report = CsvAnalyzer().scan(path)
    assert "csv_zero_width_payload" in _mechanisms(report)


def test_zero_width_payload_recovers_payload(tmp_path: Path) -> None:
    """Recovered cell value (with ZWSP codepoint) appears in concealed."""
    cell_value = f"HIDDEN_TEXT_PAYLOAD: {_ZWSP}actual revenue $10,000"
    data = _csv_bytes(
        "sku,description",
        f'A001,"{cell_value}"',
    )
    path = _write(tmp_path, "zw_recover.csv", data)
    report = CsvAnalyzer().scan(path)
    findings = _findings(report, "csv_zero_width_payload")
    assert findings
    concealed_text = " ".join(f.concealed for f in findings)
    assert "HIDDEN_TEXT_PAYLOAD" in concealed_text
    assert "10,000" in concealed_text
    # Verify the ZWSP codepoint is reported in the description.
    desc_text = " ".join(f.description for f in findings)
    assert "U+200B" in desc_text


def test_zero_width_payload_clean_control(tmp_path: Path) -> None:
    """A clean ASCII CSV emits no csv_zero_width_payload finding."""
    data = _csv_bytes(
        "sku,description",
        "A001,clean text",
        "A002,more clean text",
    )
    path = _write(tmp_path, "zw_clean.csv", data)
    report = CsvAnalyzer().scan(path)
    assert "csv_zero_width_payload" not in _mechanisms(report)


def test_zero_width_payload_silent_on_leading_bom(tmp_path: Path) -> None:
    """A file-start BOM (U+FEFF at byte 0) does NOT fire
    csv_zero_width_payload. The base CSV decoder strips the leading
    BOM before the per-cell scan runs, so the per-cell detector
    only sees mid-stream U+FEFF (which IS a payload). Legitimate
    UTF-8 BOM-prefixed files must remain silent on this mechanism.
    """
    # Encode with utf-8-sig to prepend the BOM at byte 0.
    body = "sku,description\r\nA001,clean cell\r\nA002,another clean cell\r\n"
    data = body.encode("utf-8-sig")
    path = _write(tmp_path, "zw_leading_bom.csv", data)
    report = CsvAnalyzer().scan(path)
    assert "csv_zero_width_payload" not in _mechanisms(report)


# ---------------------------------------------------------------------------
# csv_encoding_divergence (new mechanism, batin)
# ---------------------------------------------------------------------------


def test_encoding_divergence_catches(tmp_path: Path) -> None:
    """A cell with high-bit bytes that decode differently under UTF-8
    vs latin-1 fires csv_encoding_divergence.

    The byte sequence b"\\xc3\\xa9" decodes to "\u00e9" under UTF-8 (one
    codepoint) and to "\u00c3\u00a9" under latin-1 (two codepoints). The
    same bytes carry different cell text on the two surfaces.
    """
    # Header line in pure ASCII to keep the divergence isolated to row 1.
    header = b"sku,description"
    # Row with a divergent byte sequence in the description column.
    row = b'A001,"caf\xc3\xa9 menu"'
    data = header + CRLF + row + CRLF
    path = _write(tmp_path, "encdiv.csv", data)
    report = CsvAnalyzer().scan(path)
    assert "csv_encoding_divergence" in _mechanisms(report)


def test_encoding_divergence_recovers_payload(tmp_path: Path) -> None:
    """Both decoded forms appear in the finding's concealed field."""
    header = b"sku,description"
    # 0xE9 is "\u00e9" in latin-1 but an invalid UTF-8 start byte.
    # Encoded as bytes b"\xe9 special" - the UTF-8 decoder will emit
    # U+FFFD for 0xE9 while latin-1 yields the literal "\u00e9".
    row = b'A001,"\xe9 special invoice"'
    data = header + CRLF + row + CRLF
    path = _write(tmp_path, "encdiv_recover.csv", data)
    report = CsvAnalyzer().scan(path)
    findings = _findings(report, "csv_encoding_divergence")
    assert findings
    # The concealed field must carry both decoded forms so a reviewer
    # can see exactly what each codec saw without re-running the scan.
    concealed_text = " ".join(f.concealed for f in findings)
    assert "UTF-8" in concealed_text
    assert "latin-1" in concealed_text


def test_encoding_divergence_clean_control(tmp_path: Path) -> None:
    """A pure-ASCII CSV emits no csv_encoding_divergence finding.

    UTF-8 and latin-1 agree byte-for-byte on the ASCII range
    (0x00..0x7F), so no field can diverge.
    """
    data = _csv_bytes(
        "sku,description",
        "A001,clean ascii cell",
        "A002,another clean ascii cell",
    )
    path = _write(tmp_path, "encdiv_clean.csv", data)
    report = CsvAnalyzer().scan(path)
    assert "csv_encoding_divergence" not in _mechanisms(report)


def test_encoding_divergence_silent_on_leading_bom(tmp_path: Path) -> None:
    """A legitimate UTF-8 BOM-prefixed file with otherwise pure-ASCII
    cells does NOT fire csv_encoding_divergence.

    The detector strips the leading BOM (matching the base decoder)
    before running the two-decode walk; the post-BOM body is pure
    ASCII, so UTF-8 and latin-1 produce byte-identical row streams.
    """
    body = "sku,description\r\nA001,clean cell\r\nA002,another clean cell\r\n"
    data = body.encode("utf-8-sig")
    path = _write(tmp_path, "encdiv_leading_bom.csv", data)
    report = CsvAnalyzer().scan(path)
    assert "csv_encoding_divergence" not in _mechanisms(report)
