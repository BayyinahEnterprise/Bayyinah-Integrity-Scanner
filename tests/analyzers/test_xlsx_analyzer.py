"""
Tests for analyzers.xlsx_analyzer.XlsxAnalyzer.

Phase 17 guardrails. XlsxAnalyzer is a dual witness — batin (VBA,
embedded objects, revision history, hidden sheets, external links,
data-validation formulas) and zahir (hidden rows/columns, plus the
shared zero-width / TAG / bidi / homoglyph detectors applied to every
cell text reached via shared strings or inline ``<is><t>``). Each
detector has a targeted unit test that builds a minimal OOXML ZIP in
``tmp_path`` and scans it.

The builders here are intentionally separate from
``tests/make_xlsx_fixtures.py``. That module produces the committed
fixture corpus; these tests build one-off ZIPs per test so each
detector can be exercised in isolation with clean pass/fail semantics.

Mirrors the structure of ``tests/analyzers/test_docx_analyzer.py``.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from analyzers import XlsxAnalyzer
from analyzers.base import BaseAnalyzer
from domain import IntegrityReport
from infrastructure.file_router import FileKind


# ---------------------------------------------------------------------------
# Contract
# ---------------------------------------------------------------------------


def test_is_base_analyzer_subclass() -> None:
    assert issubclass(XlsxAnalyzer, BaseAnalyzer)


def test_class_attributes() -> None:
    assert XlsxAnalyzer.name == "xlsx"
    assert XlsxAnalyzer.error_prefix == "XLSX scan error"
    # Class-level source_layer is batin for scan_error attribution.
    # Per-finding source_layer is set explicitly when emitted.
    assert XlsxAnalyzer.source_layer == "batin"


def test_supported_kinds_is_xlsx_only() -> None:
    assert XlsxAnalyzer.supported_kinds == frozenset({FileKind.XLSX})


# ---------------------------------------------------------------------------
# Minimal OOXML / SpreadsheetML skeleton helpers (kept local to this module)
# ---------------------------------------------------------------------------


_FIXED_DT = (2026, 4, 22, 0, 0, 0)

_S_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

_CONTENT_TYPES_MIN = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" '
    'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/xl/workbook.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.'
    'spreadsheetml.sheet.main+xml"/>'
    '<Override PartName="/xl/worksheets/sheet1.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.'
    'spreadsheetml.worksheet+xml"/>'
    '<Override PartName="/xl/sharedStrings.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.'
    'spreadsheetml.sharedStrings+xml"/>'
    '</Types>'
)

_ROOT_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/'
    'package/2006/relationships">'
    '<Relationship Id="rId1" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/'
    'relationships/officeDocument" Target="xl/workbook.xml"/>'
    '</Relationships>'
)

_WB_RELS_DEFAULT = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/'
    'package/2006/relationships">'
    '<Relationship Id="rId1" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/'
    'relationships/worksheet" Target="worksheets/sheet1.xml"/>'
    '<Relationship Id="rId2" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/'
    'relationships/sharedStrings" Target="sharedStrings.xml"/>'
    '</Relationships>'
)

_SHEETS_DEFAULT = '<sheet name="Sheet1" sheetId="1" r:id="rId1"/>'


def _add(zf: zipfile.ZipFile, name: str, data: bytes | str) -> None:
    if isinstance(data, str):
        data = data.encode("utf-8")
    info = zipfile.ZipInfo(filename=name, date_time=_FIXED_DT)
    info.compress_type = zipfile.ZIP_STORED
    zf.writestr(info, data)


def _workbook_xml(sheets_inner: str = _SHEETS_DEFAULT) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<workbook xmlns="{_S_NS}" xmlns:r="{_R_NS}">'
        f'<sheets>{sheets_inner}</sheets>'
        '</workbook>'
    )


def _worksheet_xml(
    *,
    cols_inner: str = "",
    sheet_data_inner: str = '<row r="1"><c r="A1" t="s"><v>0</v></c></row>',
    extras_after: str = "",
) -> str:
    cols_block = f'<cols>{cols_inner}</cols>' if cols_inner else ""
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<worksheet xmlns="{_S_NS}">'
        f'{cols_block}'
        f'<sheetData>{sheet_data_inner}</sheetData>'
        f'{extras_after}'
        '</worksheet>'
    )


def _shared_strings_xml(strings: list[str]) -> str:
    items = "".join(
        f'<si><t xml:space="preserve">{s}</t></si>' for s in strings
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<sst xmlns="{_S_NS}" count="{len(strings)}" '
        f'uniqueCount="{len(strings)}">{items}</sst>'
    )


def _build_xlsx(
    path: Path,
    *,
    content_types: str = _CONTENT_TYPES_MIN,
    wb_rels: str = _WB_RELS_DEFAULT,
    sheets_inner: str = _SHEETS_DEFAULT,
    worksheet_xml: str | None = None,
    shared_strings: list[str] | None = None,
    extra_entries: list[tuple[str, bytes | str]] | None = None,
) -> Path:
    """Write a minimal .xlsx to ``path`` and return the path."""
    if shared_strings is None:
        shared_strings = ["Clean content"]
    if worksheet_xml is None:
        worksheet_xml = _worksheet_xml()
    with zipfile.ZipFile(path, "w") as zf:
        _add(zf, "[Content_Types].xml", content_types)
        _add(zf, "_rels/.rels", _ROOT_RELS)
        _add(zf, "xl/_rels/workbook.xml.rels", wb_rels)
        _add(zf, "xl/workbook.xml", _workbook_xml(sheets_inner))
        _add(zf, "xl/worksheets/sheet1.xml", worksheet_xml)
        _add(zf, "xl/sharedStrings.xml", _shared_strings_xml(shared_strings))
        for name, data in (extra_entries or []):
            _add(zf, name, data)
    return path


def _scan(path: Path) -> IntegrityReport:
    return XlsxAnalyzer().scan(path)


def _mechs(report: IntegrityReport) -> list[str]:
    return [f.mechanism for f in report.findings]


# ---------------------------------------------------------------------------
# Clean input
# ---------------------------------------------------------------------------


def test_clean_xlsx_produces_no_findings(tmp_path: Path) -> None:
    p = _build_xlsx(
        tmp_path / "clean.xlsx",
        shared_strings=["Ordinary plain body text."],
    )
    r = _scan(p)
    assert r.findings == []
    assert r.integrity_score == 1.0


# ---------------------------------------------------------------------------
# Batin — VBA macros (priority 1)
# ---------------------------------------------------------------------------


def test_vba_macros_fires_on_vbaproject_entry(tmp_path: Path) -> None:
    p = _build_xlsx(
        tmp_path / "vba.xlsx",
        extra_entries=[("xl/vbaProject.bin", b"MACRO_BINARY")],
    )
    r = _scan(p)
    assert "xlsx_vba_macros" in _mechs(r)
    vba = next(f for f in r.findings if f.mechanism == "xlsx_vba_macros")
    assert vba.source_layer == "batin"
    assert vba.confidence == 1.0


def test_vba_macros_silent_when_absent(tmp_path: Path) -> None:
    p = _build_xlsx(tmp_path / "no_vba.xlsx")
    assert "xlsx_vba_macros" not in _mechs(_scan(p))


# ---------------------------------------------------------------------------
# Batin — embedded objects (priority 1)
# ---------------------------------------------------------------------------


def test_embedded_object_fires_once_per_embedding(tmp_path: Path) -> None:
    p = _build_xlsx(
        tmp_path / "embedded.xlsx",
        extra_entries=[
            ("xl/embeddings/oleObject1.bin", b"FIRST"),
            ("xl/embeddings/oleObject2.bin", b"SECOND"),
        ],
    )
    r = _scan(p)
    embedded = [f for f in r.findings if f.mechanism == "xlsx_embedded_object"]
    assert len(embedded) == 2
    assert all(f.source_layer == "batin" for f in embedded)


def test_embedded_object_silent_when_absent(tmp_path: Path) -> None:
    p = _build_xlsx(tmp_path / "no_embedded.xlsx")
    assert "xlsx_embedded_object" not in _mechs(_scan(p))


# ---------------------------------------------------------------------------
# Batin — revision history (priority 2)
# ---------------------------------------------------------------------------


def test_revision_history_fires_once_per_workbook(tmp_path: Path) -> None:
    p = _build_xlsx(
        tmp_path / "rev.xlsx",
        extra_entries=[
            ("xl/revisions/revisionHeaders.xml",
             f'<?xml version="1.0"?><headers xmlns="{_S_NS}"/>'),
            ("xl/revisions/revisionLog1.xml",
             f'<?xml version="1.0"?><revisions xmlns="{_S_NS}"/>'),
        ],
    )
    r = _scan(p)
    rev = [f for f in r.findings if f.mechanism == "xlsx_revision_history"]
    # Rolled up: one finding per workbook regardless of revision part count.
    assert len(rev) == 1
    assert rev[0].source_layer == "batin"


def test_revision_history_silent_on_clean_workbook(tmp_path: Path) -> None:
    p = _build_xlsx(tmp_path / "clean.xlsx")
    assert "xlsx_revision_history" not in _mechs(_scan(p))


# ---------------------------------------------------------------------------
# Batin — hidden sheets (priority 2)
# ---------------------------------------------------------------------------


def test_hidden_sheet_fires_on_state_hidden(tmp_path: Path) -> None:
    sheets = (
        '<sheet name="Visible" sheetId="1" r:id="rId1"/>'
        '<sheet name="Secret" sheetId="2" r:id="rId1" state="hidden"/>'
    )
    p = _build_xlsx(
        tmp_path / "hidden.xlsx",
        sheets_inner=sheets,
    )
    r = _scan(p)
    hs = [f for f in r.findings if f.mechanism == "xlsx_hidden_sheet"]
    assert len(hs) == 1
    assert "Secret" in hs[0].description
    assert hs[0].source_layer == "batin"


def test_hidden_sheet_fires_on_state_very_hidden(tmp_path: Path) -> None:
    sheets = (
        '<sheet name="Visible" sheetId="1" r:id="rId1"/>'
        '<sheet name="Deep" sheetId="2" r:id="rId1" state="veryHidden"/>'
    )
    p = _build_xlsx(
        tmp_path / "very_hidden.xlsx",
        sheets_inner=sheets,
    )
    r = _scan(p)
    hs = [f for f in r.findings if f.mechanism == "xlsx_hidden_sheet"]
    assert len(hs) == 1
    # The description carries the state-specific note about the VBA IDE.
    assert "VBA IDE" in hs[0].description


def test_hidden_sheet_silent_when_all_visible(tmp_path: Path) -> None:
    p = _build_xlsx(tmp_path / "visible.xlsx")
    assert "xlsx_hidden_sheet" not in _mechs(_scan(p))


# ---------------------------------------------------------------------------
# Batin — external links (priority 3)
# ---------------------------------------------------------------------------


def test_external_link_fires_on_externallinks_part(tmp_path: Path) -> None:
    p = _build_xlsx(
        tmp_path / "extlink_part.xlsx",
        extra_entries=[
            ("xl/externalLinks/externalLink1.xml",
             f'<?xml version="1.0"?><externalLink xmlns="{_S_NS}"/>'),
        ],
    )
    r = _scan(p)
    ext = [f for f in r.findings if f.mechanism == "xlsx_external_link"]
    assert len(ext) >= 1
    assert ext[0].source_layer == "batin"


def test_external_link_fires_on_external_targetmode(tmp_path: Path) -> None:
    """A TargetMode="External" relationship in any .rels part must fire."""
    wb_rels_with_ext = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/'
        'package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/'
        '2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '<Relationship Id="rId2" '
        'Type="http://schemas.openxmlformats.org/officeDocument/'
        '2006/relationships/sharedStrings" Target="sharedStrings.xml"/>'
        '<Relationship Id="rId_ext1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/'
        '2006/relationships/externalLink" '
        'Target="https://example.invalid/remote.xlsx" TargetMode="External"/>'
        '</Relationships>'
    )
    p = _build_xlsx(
        tmp_path / "extlink_rel.xlsx",
        wb_rels=wb_rels_with_ext,
    )
    r = _scan(p)
    ext = [f for f in r.findings if f.mechanism == "xlsx_external_link"]
    assert len(ext) == 1
    assert "example.invalid" in ext[0].description


def test_internal_relationship_does_not_fire_external(tmp_path: Path) -> None:
    """Internal rels (no ``TargetMode="External"``) must stay silent."""
    p = _build_xlsx(tmp_path / "internal.xlsx")
    assert "xlsx_external_link" not in _mechs(_scan(p))


# ---------------------------------------------------------------------------
# Zahir — hidden rows / columns
# ---------------------------------------------------------------------------


def test_hidden_row_fires(tmp_path: Path) -> None:
    sheet_data = (
        '<row r="1"><c r="A1" t="s"><v>0</v></c></row>'
        '<row r="2" hidden="1"><c r="A2" t="s"><v>0</v></c></row>'
    )
    p = _build_xlsx(
        tmp_path / "hidden_row.xlsx",
        worksheet_xml=_worksheet_xml(sheet_data_inner=sheet_data),
    )
    r = _scan(p)
    hrc = [f for f in r.findings if f.mechanism == "xlsx_hidden_row_column"]
    assert len(hrc) == 1
    assert hrc[0].source_layer == "zahir"


def test_hidden_column_fires(tmp_path: Path) -> None:
    cols_inner = '<col min="3" max="5" hidden="1"/>'
    p = _build_xlsx(
        tmp_path / "hidden_col.xlsx",
        worksheet_xml=_worksheet_xml(cols_inner=cols_inner),
    )
    r = _scan(p)
    hrc = [f for f in r.findings if f.mechanism == "xlsx_hidden_row_column"]
    assert len(hrc) == 1
    assert hrc[0].source_layer == "zahir"


def test_hidden_row_column_silent_when_absent(tmp_path: Path) -> None:
    p = _build_xlsx(tmp_path / "no_hidden.xlsx")
    assert "xlsx_hidden_row_column" not in _mechs(_scan(p))


# ---------------------------------------------------------------------------
# Batin — data-validation formulas
# ---------------------------------------------------------------------------


def test_data_validation_formula_fires_on_indirect(tmp_path: Path) -> None:
    extras_after = (
        '<dataValidations count="1">'
        '<dataValidation type="list" sqref="A1">'
        '<formula1>INDIRECT("[remote.xlsx]Sheet1!A1")</formula1>'
        '</dataValidation>'
        '</dataValidations>'
    )
    p = _build_xlsx(
        tmp_path / "dv_indirect.xlsx",
        worksheet_xml=_worksheet_xml(extras_after=extras_after),
    )
    r = _scan(p)
    dv = [f for f in r.findings if f.mechanism == "xlsx_data_validation_formula"]
    assert len(dv) == 1
    assert dv[0].source_layer == "batin"
    # INDIRECT is present in the formula preview within the description.
    assert "INDIRECT" in dv[0].description


def test_data_validation_formula_fires_on_hyperlink(tmp_path: Path) -> None:
    extras_after = (
        '<dataValidations count="1">'
        '<dataValidation type="custom" sqref="B2">'
        '<formula1>HYPERLINK("https://example.invalid")</formula1>'
        '</dataValidation>'
        '</dataValidations>'
    )
    p = _build_xlsx(
        tmp_path / "dv_hyperlink.xlsx",
        worksheet_xml=_worksheet_xml(extras_after=extras_after),
    )
    r = _scan(p)
    assert "xlsx_data_validation_formula" in _mechs(_scan(p))
    dv = [f for f in r.findings if f.mechanism == "xlsx_data_validation_formula"]
    assert dv[0].source_layer == "batin"


def test_data_validation_formula_silent_on_plain_numeric_rule(
    tmp_path: Path,
) -> None:
    """A plain numeric-range validation must NOT fire.

    A ``<formula1>3</formula1>`` numeric-range rule is the overwhelmingly
    common benign case. If this fires, the mechanism will drown in
    false positives on any real-world corpus.
    """
    extras_after = (
        '<dataValidations count="1">'
        '<dataValidation type="whole" operator="greaterThan" sqref="A1">'
        '<formula1>3</formula1>'
        '</dataValidation>'
        '</dataValidations>'
    )
    p = _build_xlsx(
        tmp_path / "dv_plain.xlsx",
        worksheet_xml=_worksheet_xml(extras_after=extras_after),
    )
    assert "xlsx_data_validation_formula" not in _mechs(_scan(p))


# ---------------------------------------------------------------------------
# Zahir — per-cell Unicode concealment (shared strings + inline)
# ---------------------------------------------------------------------------


def test_zero_width_in_shared_string_fires(tmp_path: Path) -> None:
    p = _build_xlsx(
        tmp_path / "zw.xlsx",
        shared_strings=["a\u200bb\u200bc"],
    )
    assert "zero_width_chars" in _mechs(_scan(p))


def test_tag_chars_in_shared_string_fires(tmp_path: Path) -> None:
    payload = "X"
    encoded = "".join(chr(0xE0000 + ord(c)) for c in payload)
    p = _build_xlsx(
        tmp_path / "tag.xlsx",
        shared_strings=["prefix" + encoded],
    )
    assert "tag_chars" in _mechs(_scan(p))


def test_bidi_control_in_shared_string_fires(tmp_path: Path) -> None:
    p = _build_xlsx(
        tmp_path / "bidi.xlsx",
        shared_strings=["L\u202eR\u202c"],
    )
    assert "bidi_control" in _mechs(_scan(p))


def test_homoglyph_in_shared_string_fires(tmp_path: Path) -> None:
    # Latin 'B' + Cyrillic 'а' (U+0430) + Latin 'nk'.
    p = _build_xlsx(
        tmp_path / "hom.xlsx",
        shared_strings=["B\u0430nk"],
    )
    assert "homoglyph" in _mechs(_scan(p))


def test_zero_width_in_inline_cell_text_fires(tmp_path: Path) -> None:
    """Inline ``<is><t>...</t></is>`` strings must be scanned too.

    Cells with ``t="inlineStr"`` hold their text inside the sheet rather
    than via a sharedStrings index. The analyzer must walk these inline
    runs and apply the zahir detectors identically.
    """
    sheet_data = (
        '<row r="1">'
        '<c r="A1" t="inlineStr">'
        '<is><t xml:space="preserve">x\u200by</t></is>'
        '</c>'
        '</row>'
    )
    p = _build_xlsx(
        tmp_path / "inline_zw.xlsx",
        worksheet_xml=_worksheet_xml(sheet_data_inner=sheet_data),
        # No shared strings entry at all — only the inline cell.
        shared_strings=[],
    )
    assert "zero_width_chars" in _mechs(_scan(p))


def test_shared_string_location_pins_si_index(tmp_path: Path) -> None:
    """A zero-width finding must identify its shared-string si index."""
    p = _build_xlsx(
        tmp_path / "loc.xlsx",
        shared_strings=["clean", "a\u200bb"],
    )
    zw = next(
        f for f in _scan(p).findings if f.mechanism == "zero_width_chars"
    )
    assert "xl/sharedStrings.xml" in zw.location
    # The offending string is the second ``<si>`` element.
    assert ":si2" in zw.location


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_non_zip_input_produces_scan_error(tmp_path: Path) -> None:
    p = tmp_path / "bad.xlsx"
    p.write_bytes(b"this is not a zip file")
    r = _scan(p)
    mechs = _mechs(r)
    assert mechs == ["scan_error"]
    assert r.scan_incomplete
    # Source layer of the scan_error finding is the class default (batin).
    assert r.findings[0].source_layer == "batin"


def test_malformed_workbook_xml_does_not_crash(tmp_path: Path) -> None:
    """A valid ZIP with invalid workbook.xml must not raise; hidden-sheet
    detection quietly returns (no workbook parse, no sheets to check)."""
    p = tmp_path / "bad_workbook.xlsx"
    with zipfile.ZipFile(p, "w") as zf:
        _add(zf, "[Content_Types].xml", _CONTENT_TYPES_MIN)
        _add(zf, "_rels/.rels", _ROOT_RELS)
        _add(zf, "xl/_rels/workbook.xml.rels", _WB_RELS_DEFAULT)
        _add(zf, "xl/workbook.xml", "<not valid xml>>")
        _add(zf, "xl/worksheets/sheet1.xml", _worksheet_xml())
        _add(zf, "xl/sharedStrings.xml", _shared_strings_xml(["body"]))
    r = _scan(p)
    assert isinstance(r, IntegrityReport)
    assert 0.0 <= r.integrity_score <= 1.0
    assert "xlsx_hidden_sheet" not in _mechs(r)


def test_malformed_sheet_xml_produces_scan_error_for_that_sheet(
    tmp_path: Path,
) -> None:
    """If a sheet part is unparsable XML, the analyzer surfaces a
    scan_error finding for that sheet (rather than crashing)."""
    p = tmp_path / "bad_sheet.xlsx"
    with zipfile.ZipFile(p, "w") as zf:
        _add(zf, "[Content_Types].xml", _CONTENT_TYPES_MIN)
        _add(zf, "_rels/.rels", _ROOT_RELS)
        _add(zf, "xl/_rels/workbook.xml.rels", _WB_RELS_DEFAULT)
        _add(zf, "xl/workbook.xml", _workbook_xml())
        _add(zf, "xl/worksheets/sheet1.xml", "<not valid xml>>")
        _add(zf, "xl/sharedStrings.xml", _shared_strings_xml(["body"]))
    r = _scan(p)
    assert any(f.mechanism == "scan_error" for f in r.findings)


def test_missing_workbook_xml_does_not_crash(tmp_path: Path) -> None:
    """An XLSX without xl/workbook.xml is malformed but should not raise
    — the analyzer simply has nothing to inspect at the workbook layer.
    """
    p = tmp_path / "no_workbook.xlsx"
    with zipfile.ZipFile(p, "w") as zf:
        _add(zf, "[Content_Types].xml", _CONTENT_TYPES_MIN)
        _add(zf, "_rels/.rels", _ROOT_RELS)
    r = _scan(p)
    assert isinstance(r, IntegrityReport)
    assert 0.0 <= r.integrity_score <= 1.0
