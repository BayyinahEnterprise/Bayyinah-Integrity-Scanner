"""
Tests for analyzers.docx_analyzer.DocxAnalyzer.

Phase 15 guardrails. DocxAnalyzer is a dual witness — batin (VBA,
embedded objects, altChunks, external relationships, revision history)
and zahir (hidden text via ``<w:vanish/>``, plus the shared
zero-width / TAG / bidi / homoglyph detectors applied to every
``<w:t>`` run). Each detector has a targeted unit test that builds a
minimal OOXML ZIP in ``tmp_path`` and scans it.

The builders here are intentionally separate from
``tests/make_docx_fixtures.py``. That module produces the committed
fixture corpus; these tests build one-off ZIPs per test so each
detector can be exercised in isolation with clean pass/fail semantics.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from analyzers import DocxAnalyzer
from analyzers.base import BaseAnalyzer
from domain import IntegrityReport
from infrastructure.file_router import FileKind


# ---------------------------------------------------------------------------
# Contract
# ---------------------------------------------------------------------------


def test_is_base_analyzer_subclass() -> None:
    assert issubclass(DocxAnalyzer, BaseAnalyzer)


def test_class_attributes() -> None:
    assert DocxAnalyzer.name == "docx"
    assert DocxAnalyzer.error_prefix == "DOCX scan error"
    # Class-level source_layer is batin for scan_error attribution.
    # Per-finding source_layer is set explicitly when emitted.
    assert DocxAnalyzer.source_layer == "batin"


def test_supported_kinds_is_docx_only() -> None:
    assert DocxAnalyzer.supported_kinds == frozenset({FileKind.DOCX})


# ---------------------------------------------------------------------------
# Minimal OOXML skeleton helpers (kept local to this test module)
# ---------------------------------------------------------------------------


_FIXED_DT = (2026, 4, 22, 0, 0, 0)

_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    '</Types>'
)
_ROOT_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
    'Target="word/document.xml"/>'
    '</Relationships>'
)
_DOC_RELS_EMPTY = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>'
)


def _add(zf: zipfile.ZipFile, name: str, data: bytes | str) -> None:
    if isinstance(data, str):
        data = data.encode("utf-8")
    info = zipfile.ZipInfo(filename=name, date_time=_FIXED_DT)
    info.compress_type = zipfile.ZIP_STORED
    zf.writestr(info, data)


def _document(body_inner: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:body>' + body_inner + '</w:body>'
        '</w:document>'
    )


def _build_docx(
    path: Path,
    body_inner: str,
    *,
    doc_rels: str = _DOC_RELS_EMPTY,
    extras: list[tuple[str, bytes]] | None = None,
) -> Path:
    """Write a minimal .docx to ``path`` and return the path."""
    with zipfile.ZipFile(path, "w") as zf:
        _add(zf, "[Content_Types].xml", _CONTENT_TYPES)
        _add(zf, "_rels/.rels", _ROOT_RELS)
        _add(zf, "word/_rels/document.xml.rels", doc_rels)
        _add(zf, "word/document.xml", _document(body_inner))
        for name, data in (extras or []):
            _add(zf, name, data)
    return path


def _run(text: str) -> str:
    return f'<w:r><w:t xml:space="preserve">{text}</w:t></w:r>'


def _vanish_run(text: str) -> str:
    return (
        '<w:r><w:rPr><w:vanish/></w:rPr>'
        f'<w:t xml:space="preserve">{text}</w:t></w:r>'
    )


def _para(*runs: str) -> str:
    return '<w:p>' + "".join(runs) + '</w:p>'


def _scan(path: Path) -> IntegrityReport:
    return DocxAnalyzer().scan(path)


def _mechs(report: IntegrityReport) -> list[str]:
    return [f.mechanism for f in report.findings]


# ---------------------------------------------------------------------------
# Clean input
# ---------------------------------------------------------------------------


def test_clean_docx_produces_no_findings(tmp_path: Path) -> None:
    p = _build_docx(
        tmp_path / "clean.docx",
        _para(_run("Ordinary plain body text.")),
    )
    r = _scan(p)
    assert r.findings == []
    assert r.integrity_score == 1.0


# ---------------------------------------------------------------------------
# Batin — VBA macros
# ---------------------------------------------------------------------------


def test_vba_macros_fires_on_vbaproject_entry(tmp_path: Path) -> None:
    p = _build_docx(
        tmp_path / "vba.docx",
        _para(_run("Body.")),
        extras=[("word/vbaProject.bin", b"MACRO_BINARY")],
    )
    r = _scan(p)
    assert "docx_vba_macros" in _mechs(r)
    vba = next(f for f in r.findings if f.mechanism == "docx_vba_macros")
    assert vba.source_layer == "batin"
    assert vba.confidence == 1.0


def test_vba_macros_silent_when_absent(tmp_path: Path) -> None:
    p = _build_docx(tmp_path / "no_vba.docx", _para(_run("Body.")))
    assert "docx_vba_macros" not in _mechs(_scan(p))


# ---------------------------------------------------------------------------
# Batin — embedded objects
# ---------------------------------------------------------------------------


def test_embedded_object_fires_once_per_embedding(tmp_path: Path) -> None:
    p = _build_docx(
        tmp_path / "embedded.docx",
        _para(_run("Body.")),
        extras=[
            ("word/embeddings/oleObject1.bin", b"FIRST"),
            ("word/embeddings/oleObject2.bin", b"SECOND"),
        ],
    )
    r = _scan(p)
    embedded = [f for f in r.findings if f.mechanism == "docx_embedded_object"]
    assert len(embedded) == 2
    assert all(f.source_layer == "batin" for f in embedded)


def test_embedded_object_silent_when_absent(tmp_path: Path) -> None:
    p = _build_docx(tmp_path / "no_embedded.docx", _para(_run("Body.")))
    assert "docx_embedded_object" not in _mechs(_scan(p))


# ---------------------------------------------------------------------------
# Batin — altChunk
# ---------------------------------------------------------------------------


_DOC_RELS_ALT_CHUNK = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId_alt1" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/aFChunk" '
    'Target="altChunk1.html"/>'
    '</Relationships>'
)


def test_alt_chunk_fires(tmp_path: Path) -> None:
    p = _build_docx(
        tmp_path / "alt.docx",
        _para(_run("Body.")),
        doc_rels=_DOC_RELS_ALT_CHUNK,
        extras=[("word/altChunk1.html", b"<html/>")],
    )
    r = _scan(p)
    alt = [f for f in r.findings if f.mechanism == "docx_alt_chunk"]
    assert len(alt) == 1
    assert "altChunk1.html" in alt[0].description
    assert alt[0].source_layer == "batin"


# ---------------------------------------------------------------------------
# Batin — external relationships
# ---------------------------------------------------------------------------


_DOC_RELS_EXTERNAL = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId_ext1" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
    'Target="https://example.invalid/tracker.png" TargetMode="External"/>'
    '</Relationships>'
)


def test_external_relationship_fires(tmp_path: Path) -> None:
    p = _build_docx(
        tmp_path / "ext.docx",
        _para(_run("Body.")),
        doc_rels=_DOC_RELS_EXTERNAL,
    )
    r = _scan(p)
    ext = [f for f in r.findings if f.mechanism == "docx_external_relationship"]
    assert len(ext) == 1
    assert "example.invalid" in ext[0].description


def test_internal_relationship_does_not_fire_external(tmp_path: Path) -> None:
    """A relationship without ``TargetMode="External"`` must not fire."""
    p = _build_docx(tmp_path / "int.docx", _para(_run("Body.")))
    assert "docx_external_relationship" not in _mechs(_scan(p))


# ---------------------------------------------------------------------------
# Batin — revision history
# ---------------------------------------------------------------------------


def test_revision_history_fires_once_per_document(tmp_path: Path) -> None:
    body = (
        '<w:p>'
        '<w:ins w:id="1" w:author="R" w:date="2026-04-22T00:00:00Z">'
        '<w:r><w:t xml:space="preserve">new </w:t></w:r>'
        '</w:ins>'
        '<w:del w:id="2" w:author="R" w:date="2026-04-22T00:00:00Z">'
        '<w:r><w:delText xml:space="preserve">old </w:delText></w:r>'
        '</w:del>'
        '<w:r><w:t xml:space="preserve">tail.</w:t></w:r>'
        '</w:p>'
    )
    p = _build_docx(tmp_path / "rev.docx", body)
    r = _scan(p)
    rev = [f for f in r.findings if f.mechanism == "docx_revision_history"]
    # One rolled-up finding per document.
    assert len(rev) == 1
    assert rev[0].source_layer == "batin"


def test_revision_history_silent_on_clean_document(tmp_path: Path) -> None:
    p = _build_docx(tmp_path / "clean.docx", _para(_run("Plain.")))
    assert "docx_revision_history" not in _mechs(_scan(p))


# ---------------------------------------------------------------------------
# Zahir — hidden text via <w:vanish/>
# ---------------------------------------------------------------------------


def test_hidden_text_fires_on_vanish_run(tmp_path: Path) -> None:
    p = _build_docx(
        tmp_path / "hidden.docx",
        _para(
            _run("Visible."),
            _vanish_run("HIDDEN PAYLOAD"),
        ),
    )
    r = _scan(p)
    hidden = [f for f in r.findings if f.mechanism == "docx_hidden_text"]
    assert len(hidden) == 1
    assert "HIDDEN PAYLOAD" in hidden[0].description
    assert hidden[0].source_layer == "zahir"


def test_hidden_text_silent_on_empty_vanish_run(tmp_path: Path) -> None:
    """A vanish-marked run with no text content should not fire."""
    p = _build_docx(
        tmp_path / "empty_vanish.docx",
        _para(_run("Visible."), _vanish_run("")),
    )
    assert "docx_hidden_text" not in _mechs(_scan(p))


# ---------------------------------------------------------------------------
# Zahir — per-run Unicode concealment
# ---------------------------------------------------------------------------


def test_zero_width_in_run_fires(tmp_path: Path) -> None:
    p = _build_docx(
        tmp_path / "zw.docx",
        _para(_run("a\u200bb\u200bc")),
    )
    assert "zero_width_chars" in _mechs(_scan(p))


def test_tag_chars_in_run_fires(tmp_path: Path) -> None:
    payload = "X"
    encoded = "".join(chr(0xE0000 + ord(c)) for c in payload)
    p = _build_docx(
        tmp_path / "tag.docx",
        _para(_run("prefix" + encoded)),
    )
    assert "tag_chars" in _mechs(_scan(p))


def test_bidi_control_in_run_fires(tmp_path: Path) -> None:
    p = _build_docx(
        tmp_path / "bidi.docx",
        _para(_run("L\u202ER\u202C")),
    )
    assert "bidi_control" in _mechs(_scan(p))


def test_homoglyph_in_run_fires(tmp_path: Path) -> None:
    # Latin 'B' + Cyrillic 'а' (U+0430) + Latin 'nk'.
    p = _build_docx(
        tmp_path / "hom.docx",
        _para(_run("B\u0430nk")),
    )
    assert "homoglyph" in _mechs(_scan(p))


def test_zahir_findings_carry_paragraph_run_location(tmp_path: Path) -> None:
    """Location should pin a zahir finding to paragraph/run coordinates."""
    p = _build_docx(
        tmp_path / "loc.docx",
        _para(_run("abc\u200bdef")),
    )
    zw = next(
        f for f in _scan(p).findings if f.mechanism == "zero_width_chars"
    )
    # Location is ``{path}:word/document.xml:p{n}:t{m}``.
    assert "word/document.xml" in zw.location
    assert ":p1:" in zw.location
    assert ":t1" in zw.location


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_non_zip_input_produces_scan_error(tmp_path: Path) -> None:
    p = tmp_path / "bad.docx"
    p.write_bytes(b"this is not a zip file")
    r = _scan(p)
    mechs = _mechs(r)
    assert mechs == ["scan_error"]
    assert r.scan_incomplete
    # Source layer of the scan_error finding is the class default (batin).
    assert r.findings[0].source_layer == "batin"


def test_malformed_document_xml_produces_scan_error(tmp_path: Path) -> None:
    """A valid ZIP containing invalid XML in document.xml should surface a
    scan_error — the document body could not be inspected, so cleanness
    cannot be inferred."""
    p = tmp_path / "bad_xml.docx"
    with zipfile.ZipFile(p, "w") as zf:
        _add(zf, "[Content_Types].xml", _CONTENT_TYPES)
        _add(zf, "_rels/.rels", _ROOT_RELS)
        _add(zf, "word/_rels/document.xml.rels", _DOC_RELS_EMPTY)
        _add(zf, "word/document.xml", "<not valid xml>>")
    r = _scan(p)
    assert any(f.mechanism == "scan_error" for f in r.findings)


def test_missing_document_xml_does_not_crash(tmp_path: Path) -> None:
    """A DOCX without word/document.xml is malformed but should not raise
    — the analyzer simply has nothing to inspect at the zahir layer.
    """
    p = tmp_path / "no_doc.docx"
    with zipfile.ZipFile(p, "w") as zf:
        _add(zf, "[Content_Types].xml", _CONTENT_TYPES)
        _add(zf, "_rels/.rels", _ROOT_RELS)
    r = _scan(p)
    # No crash — we either get no findings or only batin-layer findings.
    # Either way, the report exists and carries a valid score.
    assert isinstance(r, IntegrityReport)
    assert 0.0 <= r.integrity_score <= 1.0
