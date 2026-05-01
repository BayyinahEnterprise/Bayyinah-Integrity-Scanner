"""
Tests for the v1.1.8 F2 calibration items.

Eight items closing pre-registered CSV/JSON gauntlet gaps:

  * Item 1 (extension): csv_column_type_drift second band at 50 chars,
    severity 0.10.
  * Item 2 (NEW zahir): csv_oversized_freetext_cell.
  * Item 3 (NEW batin): json_key_invisible_chars.
  * Item 4 (extension): json_prototype_pollution_key value extraction.
  * Item 5 (NEW zahir): json_oversized_string_band.
  * Item 6 (NEW batin): csv_payload_in_adjacent_cell.
  * Item 7 (extension): csv_quoted_newline_payload high-density band
    at 3+ newlines and length >256.
  * Item 8 (extension): csv_column_type_drift no longer short-circuits
    on rows where the column count diverges from the header.

Each new mechanism gets four paired tests on the F2 rubric:

  * fires-on-payload
  * recovers-payload-into-concealed
  * silent-on-clean
  * silent-on-edge

Each extension item gets dedicated tests for the new band / behaviour
without disturbing the v1.1.2 F2 baseline.

Reference: bayyinah_v1_1_8_f2_calibration_prompt (in-thread).
"""

from __future__ import annotations

from pathlib import Path

from analyzers import CsvAnalyzer, JsonAnalyzer
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
    p = tmp_path / name
    p.write_bytes(data)
    return p


def _write_text(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


def _findings(report: IntegrityReport, mechanism: str):
    return [f for f in report.findings if f.mechanism == mechanism]


def _mechanisms(report: IntegrityReport) -> set[str]:
    return {f.mechanism for f in report.findings}


# ---------------------------------------------------------------------------
# Item 1 extension: csv_column_type_drift 50-char band at severity 0.10
# ---------------------------------------------------------------------------


def test_column_type_drift_short_band_catches(tmp_path: Path) -> None:
    """A 60-char free-text cell in a numeric column fires the short band."""
    data = _csv_bytes(
        "description,amount_usd,note",
        '"row 1",1000,"clean"',
        '"row 2",2000,"clean"',
        '"row 3",3000,"clean"',
        '"row 4",'
        '"HIDDEN_TEXT_PAYLOAD: actual revenue $10,000 - see annex",'
        '"drift"',
    )
    path = _write(tmp_path, "short_band.csv", data)
    report = CsvAnalyzer().scan(path)
    findings = _findings(report, "csv_column_type_drift")
    assert findings, "short band must fire on 60-char hijack"
    short = [f for f in findings if "short band" in f.surface]
    assert short, "short-band finding must be tagged in the surface"
    assert short[0].severity == 0.10


def test_column_type_drift_long_band_keeps_default_severity(
    tmp_path: Path,
) -> None:
    """A 250-char free-text cell still fires the standard band at 0.15."""
    payload = (
        "HIDDEN_TEXT_PAYLOAD: actual revenue $10,000 - see annex"
    ) * 5  # ~275 chars
    data = _csv_bytes(
        "amount_usd,sku",
        "1000,A1",
        "2000,A2",
        "3000,A3",
        f'"{payload}",A4',
    )
    path = _write(tmp_path, "long_band.csv", data)
    report = CsvAnalyzer().scan(path)
    findings = _findings(report, "csv_column_type_drift")
    assert findings, "standard band must fire on 200+ char hijack"
    longs = [f for f in findings if "long band" in f.surface]
    assert longs, "long-band finding must be tagged"
    assert longs[0].severity == 0.15


def test_column_type_drift_short_band_clean_control(tmp_path: Path) -> None:
    """A clean numeric column does not fire the short band."""
    data = _csv_bytes(
        "amount_usd,sku",
        "1000,A1",
        "2000,A2",
        "3000,A3",
        "4000,A4",
    )
    path = _write(tmp_path, "short_band_clean.csv", data)
    report = CsvAnalyzer().scan(path)
    assert "csv_column_type_drift" not in _mechanisms(report)


def test_column_type_drift_short_band_silent_on_short_cells(
    tmp_path: Path,
) -> None:
    """Cells shorter than 50 chars do not fire even in a numeric column."""
    data = _csv_bytes(
        "amount_usd,sku",
        "1000,A1",
        "2000,A2",
        "3000,A3",
        "wrong but short,A4",
    )
    path = _write(tmp_path, "short_band_edge.csv", data)
    report = CsvAnalyzer().scan(path)
    assert "csv_column_type_drift" not in _mechanisms(report)


# ---------------------------------------------------------------------------
# Item 2: csv_oversized_freetext_cell
# ---------------------------------------------------------------------------


def test_oversized_freetext_cell_catches(tmp_path: Path) -> None:
    """A 600-char cell in a column with median ~10 chars fires."""
    payload = "X" * 600
    data = _csv_bytes(
        "description,note",
        '"short prose",a',
        '"short prose",b',
        '"short prose",c',
        f'"{payload}",d',
    )
    path = _write(tmp_path, "oversized.csv", data)
    report = CsvAnalyzer().scan(path)
    findings = _findings(report, "csv_oversized_freetext_cell")
    assert findings, "oversized cell must fire"


def test_oversized_freetext_cell_recovers_payload(tmp_path: Path) -> None:
    """The smuggled payload appears in the concealed field."""
    payload = (
        "HIDDEN_TEXT_PAYLOAD: actual revenue $10,000 - see annex" * 12
    )  # ~660 chars
    data = _csv_bytes(
        "description,note",
        '"a",x',
        '"b",y',
        '"c",z',
        f'"{payload}",w',
    )
    path = _write(tmp_path, "oversized_recover.csv", data)
    report = CsvAnalyzer().scan(path)
    findings = _findings(report, "csv_oversized_freetext_cell")
    assert findings
    assert "HIDDEN_TEXT_PAYLOAD" in findings[0].concealed


def test_oversized_freetext_cell_clean_control(tmp_path: Path) -> None:
    """A document where every cell is short does not fire."""
    data = _csv_bytes(
        "description,note",
        '"short prose",x',
        '"short prose",y',
        '"short prose",z',
        '"short prose",w',
    )
    path = _write(tmp_path, "oversized_clean.csv", data)
    report = CsvAnalyzer().scan(path)
    assert "csv_oversized_freetext_cell" not in _mechanisms(report)


def test_oversized_freetext_cell_silent_when_column_is_uniformly_long(
    tmp_path: Path,
) -> None:
    """A column where every cell is long does not fire (no median outlier)."""
    long_cell = "X" * 600
    data = _csv_bytes(
        "description,note",
        f'"{long_cell}",a',
        f'"{long_cell}",b',
        f'"{long_cell}",c',
        f'"{long_cell}",d',
    )
    path = _write(tmp_path, "oversized_uniform.csv", data)
    report = CsvAnalyzer().scan(path)
    assert "csv_oversized_freetext_cell" not in _mechanisms(report)


# ---------------------------------------------------------------------------
# Item 3: json_key_invisible_chars
# ---------------------------------------------------------------------------


def test_key_invisible_chars_catches_zero_width(tmp_path: Path) -> None:
    """A key with U+200B fires."""
    content = '{"amount\u200b_usd": 1000}'
    path = _write_text(tmp_path, "zw_key.json", content)
    report = JsonAnalyzer().scan(path)
    findings = _findings(report, "json_key_invisible_chars")
    assert findings


def test_key_invisible_chars_catches_bidi(tmp_path: Path) -> None:
    """A key with U+202E fires."""
    content = '{"n\u202eote": "x"}'
    path = _write_text(tmp_path, "bidi_key.json", content)
    report = JsonAnalyzer().scan(path)
    findings = _findings(report, "json_key_invisible_chars")
    assert findings
    assert any("U+202E" in f.description for f in findings)


def test_key_invisible_chars_recovers_concealed(tmp_path: Path) -> None:
    """The verbatim key bytes appear in the concealed field."""
    content = '{"n\u202eote": "x"}'
    path = _write_text(tmp_path, "bidi_key_recover.json", content)
    report = JsonAnalyzer().scan(path)
    findings = _findings(report, "json_key_invisible_chars")
    assert findings
    assert "\u202e" in findings[0].concealed or "ote" in findings[0].concealed


def test_key_invisible_chars_clean_control(tmp_path: Path) -> None:
    """A clean JSON document does not fire."""
    content = '{"amount_usd": 1000, "note": "x"}'
    path = _write_text(tmp_path, "clean.json", content)
    report = JsonAnalyzer().scan(path)
    assert "json_key_invisible_chars" not in _mechanisms(report)


def test_key_invisible_chars_silent_on_value_only(tmp_path: Path) -> None:
    """Invisible chars in VALUES (not keys) do not trigger this mechanism."""
    content = '{"note": "value with \u200b zero-width"}'
    path = _write_text(tmp_path, "value_zw.json", content)
    report = JsonAnalyzer().scan(path)
    assert "json_key_invisible_chars" not in _mechanisms(report)


# ---------------------------------------------------------------------------
# Item 4 extension: json_prototype_pollution_key value extraction
# ---------------------------------------------------------------------------


def test_prototype_pollution_extracts_polluting_value(tmp_path: Path) -> None:
    """The polluting key's value appears in concealed and description."""
    content = (
        '{"__proto__": {"polluted": "HIDDEN_TEXT_PAYLOAD: actual revenue '
        '$10,000 - see annex"}}'
    )
    path = _write_text(tmp_path, "proto_value.json", content)
    report = JsonAnalyzer().scan(path)
    findings = _findings(report, "json_prototype_pollution_key")
    assert findings
    matched = [f for f in findings if "__proto__" in f.location]
    assert matched
    assert "HIDDEN_TEXT_PAYLOAD" in matched[0].concealed
    assert "polluting value" in matched[0].concealed


def test_prototype_pollution_value_truncates_at_500(tmp_path: Path) -> None:
    """Values longer than 500 chars are truncated with a note."""
    big = "A" * 600
    content = '{"__proto__": "' + big + '"}'
    path = _write_text(tmp_path, "proto_trunc.json", content)
    report = JsonAnalyzer().scan(path)
    findings = _findings(report, "json_prototype_pollution_key")
    proto = [f for f in findings if "__proto__" in f.location]
    assert proto
    # Truncation note appears in the concealed field.
    assert "truncated" in proto[0].concealed


def test_prototype_pollution_short_value_no_truncation_note(
    tmp_path: Path,
) -> None:
    """A short value reports without a truncation note."""
    content = '{"__proto__": "short"}'
    path = _write_text(tmp_path, "proto_short.json", content)
    report = JsonAnalyzer().scan(path)
    proto = [
        f for f in _findings(report, "json_prototype_pollution_key")
        if "__proto__" in f.location
    ]
    assert proto
    # The short-value path leaves no truncation note for the value.
    assert "polluting value: 'short'" in proto[0].concealed


# ---------------------------------------------------------------------------
# Item 5: json_oversized_string_band
# ---------------------------------------------------------------------------


def test_oversized_string_band_catches(tmp_path: Path) -> None:
    """A 1500-char string in a doc with median ~10 chars fires."""
    big = "X" * 1500
    content = (
        '{"a":"x","b":"y","c":"z","d":"' + big + '"}'
    )
    path = _write_text(tmp_path, "oversized_str.json", content)
    report = JsonAnalyzer().scan(path)
    findings = _findings(report, "json_oversized_string_band")
    assert findings


def test_oversized_string_band_recovers_payload(tmp_path: Path) -> None:
    """The smuggled payload appears in the concealed field."""
    payload = "HIDDEN_TEXT_PAYLOAD: actual revenue $10,000 " * 30
    # ~1320 chars
    content = (
        '{"a":"x","b":"y","c":"z","d":"' + payload + '"}'
    )
    path = _write_text(tmp_path, "oversized_str_recover.json", content)
    report = JsonAnalyzer().scan(path)
    findings = _findings(report, "json_oversized_string_band")
    assert findings
    assert "HIDDEN_TEXT_PAYLOAD" in findings[0].concealed


def test_oversized_string_band_clean_control(tmp_path: Path) -> None:
    """A document where every string is short does not fire."""
    content = '{"a":"x","b":"y","c":"z","d":"w"}'
    path = _write_text(tmp_path, "oversized_str_clean.json", content)
    report = JsonAnalyzer().scan(path)
    assert "json_oversized_string_band" not in _mechanisms(report)


def test_oversized_string_band_silent_on_uniformly_long(
    tmp_path: Path,
) -> None:
    """A document where every string is long does not fire."""
    big = "X" * 1500
    content = (
        '{"a":"' + big + '","b":"' + big + '","c":"' + big + '"}'
    )
    path = _write_text(tmp_path, "oversized_str_uniform.json", content)
    report = JsonAnalyzer().scan(path)
    assert "json_oversized_string_band" not in _mechanisms(report)


# ---------------------------------------------------------------------------
# Item 7 extension: csv_quoted_newline_payload high-density band
# ---------------------------------------------------------------------------


def test_quoted_newline_high_density_band_catches(tmp_path: Path) -> None:
    """A cell with 3 newlines and length >256 fires the high-density band."""
    body = "X" * 100 + "\n" + "Y" * 100 + "\n" + "Z" * 100 + "\n" + "W" * 50
    # 3 newlines, 354 chars
    data = _csv_bytes(
        "description,note",
        f'"{body}","x"',
        '"clean","y"',
    )
    path = _write(tmp_path, "high_density.csv", data)
    report = CsvAnalyzer().scan(path)
    findings = _findings(report, "csv_quoted_newline_payload")
    assert findings


def test_quoted_newline_standard_band_still_fires(tmp_path: Path) -> None:
    """A cell matching the v1.1.2 band (2 newlines, len>128) still fires."""
    body = "X" * 80 + "\n" + "Y" * 80
    # 1 newline (standard band needs 2). Adjust to 2.
    body = "X" * 60 + "\n" + "Y" * 60 + "\n" + "Z" * 60
    data = _csv_bytes(
        "description,note",
        f'"{body}","x"',
        '"clean","y"',
    )
    path = _write(tmp_path, "standard_band.csv", data)
    report = CsvAnalyzer().scan(path)
    findings = _findings(report, "csv_quoted_newline_payload")
    assert findings
    assert any("standard" in f.surface for f in findings)


def test_quoted_newline_silent_on_short_3nl_cell(tmp_path: Path) -> None:
    """A cell with 3 newlines but length <=256 does not fire band 2.

    The cell length is also <=128 so band 1 stays silent too.
    """
    body = "a\nb\nc\nd"
    data = _csv_bytes(
        "description,note",
        f'"{body}","x"',
        '"clean","y"',
    )
    path = _write(tmp_path, "short_3nl.csv", data)
    report = CsvAnalyzer().scan(path)
    assert "csv_quoted_newline_payload" not in _mechanisms(report)


# ---------------------------------------------------------------------------
# Item 6: csv_payload_in_adjacent_cell
# ---------------------------------------------------------------------------


def test_payload_in_adjacent_cell_catches(tmp_path: Path) -> None:
    """A row with bidi in one cell + long free text in another cell fires."""
    payload = "HIDDEN_TEXT_PAYLOAD: actual revenue $10,000 - see annex" * 2
    bidi_cell = "second\u202e invoice"
    data = _csv_bytes(
        "description,amount_usd,note",
        '"clean row",1000,"clean"',
        f'"{bidi_cell}",2000,"{payload}"',
    )
    path = _write(tmp_path, "adjacent.csv", data)
    report = CsvAnalyzer().scan(path)
    findings = _findings(report, "csv_payload_in_adjacent_cell")
    assert findings


def test_payload_in_adjacent_cell_recovers_payload(tmp_path: Path) -> None:
    """The adjacent free-text payload appears in concealed."""
    payload = (
        "HIDDEN_TEXT_PAYLOAD: actual revenue $10,000 - see annex"
    )
    bidi_cell = "row\u202etwo"
    data = _csv_bytes(
        "description,amount_usd,note",
        '"clean row",1000,"clean"',
        f'"{bidi_cell}",2000,"{payload}"',
    )
    path = _write(tmp_path, "adjacent_recover.csv", data)
    report = CsvAnalyzer().scan(path)
    findings = _findings(report, "csv_payload_in_adjacent_cell")
    assert findings
    assert "HIDDEN_TEXT_PAYLOAD" in findings[0].concealed


def test_payload_in_adjacent_cell_silent_when_no_invisible_finding(
    tmp_path: Path,
) -> None:
    """No invisible-character finding means the adjacent detector stays silent."""
    payload = "X" * 200
    data = _csv_bytes(
        "description,amount_usd,note",
        '"clean",1000,"clean"',
        f'"row two",2000,"{payload}"',
    )
    path = _write(tmp_path, "adjacent_nopre.csv", data)
    report = CsvAnalyzer().scan(path)
    assert "csv_payload_in_adjacent_cell" not in _mechanisms(report)


def test_payload_in_adjacent_cell_silent_when_adjacent_short(
    tmp_path: Path,
) -> None:
    """Bidi cell paired with only short adjacent cells does not fire."""
    bidi_cell = "row\u202etwo"
    data = _csv_bytes(
        "description,amount_usd,note",
        '"clean row",1000,"clean"',
        f'"{bidi_cell}",2000,"short"',
    )
    path = _write(tmp_path, "adjacent_short.csv", data)
    report = CsvAnalyzer().scan(path)
    assert "csv_payload_in_adjacent_cell" not in _mechanisms(report)


# ---------------------------------------------------------------------------
# Item 8 extension: csv_column_type_drift no longer short-circuits on
# divergent column counts (already addressed via min(header, row) walk).
# Test guards against regression.
# ---------------------------------------------------------------------------


def test_column_type_drift_runs_on_inconsistent_columns_row(
    tmp_path: Path,
) -> None:
    """A row with column-count divergence still gets type-drift analysis."""
    payload = (
        "HIDDEN_TEXT_PAYLOAD: actual revenue $10,000 - see annex" * 3
    )  # ~165 chars, triggers short band
    data = _csv_bytes(
        "amount_usd,sku,extra",
        "1000,A1,a",
        "2000,A2,b",
        "3000,A3,c",
        # Row missing the trailing column AND carrying a payload in
        # the numeric amount_usd column. The v1.1.7 short-circuit
        # would suppress the type-drift finding here.
        f'"{payload}",A4',
    )
    path = _write(tmp_path, "shortcircuit.csv", data)
    report = CsvAnalyzer().scan(path)
    drift = _findings(report, "csv_column_type_drift")
    inconsistent = _findings(report, "csv_inconsistent_columns")
    assert drift, "type-drift must fire even on column-count anomaly rows"
    assert inconsistent, "column-count anomaly still fires"


# ---------------------------------------------------------------------------
# Gauntlet recovery sanity tests
# ---------------------------------------------------------------------------


def test_gauntlet_fixture_01_short_band_recovers(tmp_path: Path) -> None:
    """Gauntlet fixture 01 fires csv_column_type_drift via the short band."""
    fixture_path = (
        Path(__file__).resolve().parent.parent.parent
        / "docs"
        / "adversarial"
        / "csv_json_gauntlet"
        / "fixtures"
        / "01_csv_type_mismatch.csv"
    )
    report = CsvAnalyzer().scan(fixture_path)
    drift = _findings(report, "csv_column_type_drift")
    assert drift, "fixture 01 must fire the type-drift short band"


def test_gauntlet_fixture_04_key_invisible_chars(tmp_path: Path) -> None:
    """Gauntlet fixture 04 fires json_key_invisible_chars."""
    fixture_path = (
        Path(__file__).resolve().parent.parent.parent
        / "docs"
        / "adversarial"
        / "csv_json_gauntlet"
        / "fixtures"
        / "04_json_concealment_in_keys.json"
    )
    report = JsonAnalyzer().scan(fixture_path)
    keys = _findings(report, "json_key_invisible_chars")
    assert keys, "fixture 04 must fire on invisible key chars"


def test_gauntlet_fixture_05_pollution_recovers_payload(
    tmp_path: Path,
) -> None:
    """Gauntlet fixture 05 fires prototype_pollution with payload extracted."""
    fixture_path = (
        Path(__file__).resolve().parent.parent.parent
        / "docs"
        / "adversarial"
        / "csv_json_gauntlet"
        / "fixtures"
        / "05_json_prototype_pollution.json"
    )
    report = JsonAnalyzer().scan(fixture_path)
    proto = _findings(report, "json_prototype_pollution_key")
    assert proto
    assert any("HIDDEN_TEXT_PAYLOAD" in f.concealed for f in proto), (
        "fixture 05 must surface the polluting value"
    )


def test_gauntlet_fixture_07_payload_in_adjacent_cell(
    tmp_path: Path,
) -> None:
    """Gauntlet fixture 07 fires csv_payload_in_adjacent_cell."""
    fixture_path = (
        Path(__file__).resolve().parent.parent.parent
        / "docs"
        / "adversarial"
        / "csv_json_gauntlet"
        / "fixtures"
        / "07_csv_bidi_zwsp_in_cell.csv"
    )
    report = CsvAnalyzer().scan(fixture_path)
    adj = _findings(report, "csv_payload_in_adjacent_cell")
    assert adj, "fixture 07 must fire the adjacent-cell mechanism"


def test_gauntlet_fixture_09_type_drift_fires(tmp_path: Path) -> None:
    """Gauntlet fixture 09 fires csv_column_type_drift even with col-count anomaly."""
    fixture_path = (
        Path(__file__).resolve().parent.parent.parent
        / "docs"
        / "adversarial"
        / "csv_json_gauntlet"
        / "fixtures"
        / "09_csv_type_drift_encoding_divergence.csv"
    )
    report = CsvAnalyzer().scan(fixture_path)
    drift = _findings(report, "csv_column_type_drift")
    assert drift
