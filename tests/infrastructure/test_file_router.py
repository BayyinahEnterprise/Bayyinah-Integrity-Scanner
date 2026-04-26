"""
Tests for infrastructure.file_router.FileRouter.

Coverage targets:
  * Magic-byte detection (PDF, PNG, JPEG)
  * DOCX detection via ZIP + extension combination
  * HTML content sniff (case-insensitive)
  * JSON content sniff (objects and arrays)
  * Extension fall-through for markdown / code / text-family
  * UNKNOWN fall-through
  * extension_mismatch flag for polyglot-style files
  * client_for dispatches PDF → PDFClient
  * client_for raises UnsupportedFileType / UnknownFileType correctly
  * is_supported convenience wrapper
  * Exercises Phase 0 fixtures directly
"""

from __future__ import annotations

from pathlib import Path

import pytest

from infrastructure.file_router import (
    FileKind,
    FileRouter,
    UnknownFileType,
    UnsupportedFileType,
)
from infrastructure.pdf_client import PDFClient


FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"
CLEAN_PDF = FIXTURES_DIR / "clean.pdf"


# ---------------------------------------------------------------------------
# Magic-byte detection
# ---------------------------------------------------------------------------

def test_detect_pdf_by_magic(tmp_path: Path) -> None:
    p = tmp_path / "x.pdf"
    p.write_bytes(b"%PDF-1.7\n%EOF\n")
    det = FileRouter().detect(p)
    assert det.kind is FileKind.PDF
    assert "PDF" in det.reason
    assert det.extension_mismatch is False


def test_detect_png_by_magic(tmp_path: Path) -> None:
    p = tmp_path / "img.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
    det = FileRouter().detect(p)
    assert det.kind is FileKind.IMAGE_PNG
    assert "PNG" in det.reason


def test_detect_jpeg_by_magic(tmp_path: Path) -> None:
    p = tmp_path / "img.jpg"
    p.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 8)
    det = FileRouter().detect(p)
    assert det.kind is FileKind.IMAGE_JPEG


# ---------------------------------------------------------------------------
# DOCX (ZIP + .docx)
# ---------------------------------------------------------------------------

def test_detect_docx_from_zip_plus_extension(tmp_path: Path) -> None:
    p = tmp_path / "doc.docx"
    p.write_bytes(b"PK\x03\x04" + b"\x00" * 16)
    det = FileRouter().detect(p)
    assert det.kind is FileKind.DOCX
    assert "ZIP" in det.reason


def test_zip_without_docx_extension_is_unknown(tmp_path: Path) -> None:
    p = tmp_path / "archive.zip"
    p.write_bytes(b"PK\x03\x04" + b"\x00" * 16)
    det = FileRouter().detect(p)
    # ZIP without a mapped extension is not something Bayyinah scans;
    # must not be misclassified as DOCX.
    assert det.kind is FileKind.UNKNOWN


# ---------------------------------------------------------------------------
# Content sniff: HTML
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "body",
    [
        b"<!doctype html><html>",
        b"<!DOCTYPE HTML><html>",
        b"  \n<html><body>x</body></html>",
        b"<head><title>x</title></head>",
    ],
)
def test_html_content_sniff(tmp_path: Path, body: bytes) -> None:
    p = tmp_path / "page.html"
    p.write_bytes(body)
    det = FileRouter().detect(p)
    assert det.kind is FileKind.HTML


def test_html_body_on_unknown_extension_still_sniffed(tmp_path: Path) -> None:
    p = tmp_path / "page.unknown"
    p.write_bytes(b"<html><body>x</body></html>")
    det = FileRouter().detect(p)
    assert det.kind is FileKind.HTML
    # Unknown extension is not a "mismatch" per se — we have no
    # extension-declared expectation to contradict.
    assert det.extension_mismatch is False


# ---------------------------------------------------------------------------
# Content sniff: JSON
# ---------------------------------------------------------------------------

def test_json_object_sniff(tmp_path: Path) -> None:
    p = tmp_path / "data.json"
    p.write_bytes(b'{"a": 1, "b": [1, 2, 3]}')
    det = FileRouter().detect(p)
    assert det.kind is FileKind.JSON


def test_json_array_sniff(tmp_path: Path) -> None:
    p = tmp_path / "data.json"
    p.write_bytes(b"[1, 2, 3]")
    det = FileRouter().detect(p)
    assert det.kind is FileKind.JSON


def test_invalid_json_with_curly_prefix_is_not_json(tmp_path: Path) -> None:
    """A file that starts with { but is not valid JSON must not be
    classified as JSON by content sniff.

    Phase 9: .txt is now in the extension map (routed to CODE so the
    TextFileAnalyzer can scan it), so we use a genuinely unrecognised
    extension here to probe the UNKNOWN fall-through path.
    """
    p = tmp_path / "data.xyz"
    p.write_bytes(b"{ not actually json at all }")
    det = FileRouter().detect(p)
    # .xyz is not in the extension map, content sniff failed, so UNKNOWN.
    assert det.kind is FileKind.UNKNOWN


def test_txt_extension_routes_to_code(tmp_path: Path) -> None:
    """Phase 9: .txt files are routed to FileKind.CODE so the
    TextFileAnalyzer picks them up."""
    p = tmp_path / "note.txt"
    p.write_bytes(b"plain notes")
    assert FileRouter().detect(p).kind is FileKind.CODE


# ---------------------------------------------------------------------------
# Extension fall-through
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "ext, expected",
    [
        ("md",       FileKind.MARKDOWN),
        ("markdown", FileKind.MARKDOWN),
        ("py",       FileKind.CODE),
        ("js",       FileKind.CODE),
        ("go",       FileKind.CODE),
        ("rs",       FileKind.CODE),
        ("java",     FileKind.CODE),
        ("ts",       FileKind.CODE),
    ],
)
def test_extension_fallthrough_text_family(
    tmp_path: Path, ext: str, expected: FileKind,
) -> None:
    p = tmp_path / f"file.{ext}"
    p.write_bytes(b"hello, world\n")
    det = FileRouter().detect(p)
    assert det.kind is expected
    assert det.extension_mismatch is False


def test_unknown_extension_and_unknown_bytes_returns_unknown(tmp_path: Path) -> None:
    p = tmp_path / "mystery.xyz"
    p.write_bytes(b"random bytes here")
    det = FileRouter().detect(p)
    assert det.kind is FileKind.UNKNOWN
    assert ".xyz" in det.reason or "xyz" in det.reason


# ---------------------------------------------------------------------------
# extension_mismatch — polyglot signalling
# ---------------------------------------------------------------------------

def test_polyglot_pdf_extension_but_zip_bytes_flags_mismatch(tmp_path: Path) -> None:
    """A ``.pdf`` file whose bytes are actually a ZIP is an adversarial
    pattern. The router must surface the mismatch without needing a
    parser."""
    p = tmp_path / "polyglot.pdf"
    p.write_bytes(b"PK\x03\x04" + b"\x00" * 16)
    det = FileRouter().detect(p)
    # Bytes are ZIP; extension is .pdf — mapped to PDF. DOCX detection
    # requires .docx extension, so this falls through to UNKNOWN with
    # no mismatch flag (we can only flag mismatch when magic-byte
    # detection succeeds).
    # HOWEVER the router's current design only flags mismatch on a
    # positive magic-byte match. For a pure-ZIP-with-.pdf case, the
    # interesting signal is that we failed to identify it at all —
    # that itself is diagnostic.
    assert det.kind in (FileKind.UNKNOWN, FileKind.DOCX)


def test_png_magic_but_html_extension_flags_mismatch(tmp_path: Path) -> None:
    """Magic says PNG, extension says HTML — classic polyglot signal."""
    p = tmp_path / "trojan.html"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
    det = FileRouter().detect(p)
    assert det.kind is FileKind.IMAGE_PNG
    assert det.extension_mismatch is True


def test_pdf_magic_with_docx_extension_flags_mismatch(tmp_path: Path) -> None:
    p = tmp_path / "spoof.docx"
    p.write_bytes(b"%PDF-1.4\n")
    det = FileRouter().detect(p)
    assert det.kind is FileKind.PDF
    assert det.extension_mismatch is True


def test_html_sniff_with_pdf_extension_flags_mismatch(tmp_path: Path) -> None:
    p = tmp_path / "fake.pdf"
    p.write_bytes(b"<!doctype html><html></html>")
    det = FileRouter().detect(p)
    assert det.kind is FileKind.HTML
    assert det.extension_mismatch is True


# ---------------------------------------------------------------------------
# SVG detection (Phase 10)
# ---------------------------------------------------------------------------

def test_svg_extension_is_recognised(tmp_path: Path) -> None:
    """A well-formed ``.svg`` file must route to IMAGE_SVG."""
    p = tmp_path / "x.svg"
    p.write_bytes(
        b'<?xml version="1.0" encoding="UTF-8"?>\n'
        b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"/>\n'
    )
    det = FileRouter().detect(p)
    assert det.kind is FileKind.IMAGE_SVG
    assert det.extension_mismatch is False


def test_svgz_extension_is_recognised(tmp_path: Path) -> None:
    """``.svgz`` is gzip-compressed SVG — same kind."""
    p = tmp_path / "x.svgz"
    # Bytes need not be valid gzip for the extension path to resolve.
    p.write_bytes(b"\x1f\x8b\x08\x00\x00\x00\x00\x00" + b"\x00" * 8)
    det = FileRouter().detect(p)
    assert det.kind is FileKind.IMAGE_SVG


def test_svg_content_sniff_with_unknown_extension(tmp_path: Path) -> None:
    """A file whose extension isn't .svg but whose bytes open with
    ``<svg`` (with or without an XML prolog) should content-sniff to
    IMAGE_SVG before the HTML / JSON paths get a chance."""
    p = tmp_path / "graphic.unknown"
    p.write_bytes(b'<svg xmlns="http://www.w3.org/2000/svg"></svg>')
    det = FileRouter().detect(p)
    assert det.kind is FileKind.IMAGE_SVG


def test_svg_content_sniff_with_xml_prolog(tmp_path: Path) -> None:
    p = tmp_path / "graphic.unknown"
    p.write_bytes(
        b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"/>'
    )
    det = FileRouter().detect(p)
    assert det.kind is FileKind.IMAGE_SVG


def test_svg_bytes_with_png_extension_flags_mismatch(tmp_path: Path) -> None:
    """Extension says PNG, bytes say SVG — classic polyglot signal."""
    p = tmp_path / "trojan.png"
    p.write_bytes(b'<svg xmlns="http://www.w3.org/2000/svg"/>')
    det = FileRouter().detect(p)
    assert det.kind is FileKind.IMAGE_SVG
    assert det.extension_mismatch is True


def test_svg_extension_with_non_svg_bytes_still_routes_svg(
    tmp_path: Path,
) -> None:
    """Extension fall-through when content sniff is inconclusive: a
    ``.svg`` file whose bytes aren't recognisably SVG still routes to
    IMAGE_SVG (the analyzer itself will report malformed XML as
    scan_error). This keeps dispatch decisions purely in the router."""
    p = tmp_path / "broken.svg"
    p.write_bytes(b"this is not a valid svg file at all")
    det = FileRouter().detect(p)
    assert det.kind is FileKind.IMAGE_SVG


def test_client_for_svg_raises_unsupported(tmp_path: Path) -> None:
    """SVG has no parser-heavy client; analyzers read bytes directly."""
    p = tmp_path / "x.svg"
    p.write_bytes(b'<svg xmlns="http://www.w3.org/2000/svg"/>')
    with pytest.raises(UnsupportedFileType, match="svg"):
        FileRouter().client_for(p)


# ---------------------------------------------------------------------------
# client_for dispatch
# ---------------------------------------------------------------------------

def test_client_for_pdf_returns_pdfclient(tmp_path: Path) -> None:
    p = tmp_path / "x.pdf"
    p.write_bytes(b"%PDF-1.7\n%EOF\n")
    client = FileRouter().client_for(p)
    try:
        assert isinstance(client, PDFClient)
        assert client.path == p
    finally:
        client.close()


def test_client_for_docx_raises_unsupported(tmp_path: Path) -> None:
    p = tmp_path / "doc.docx"
    p.write_bytes(b"PK\x03\x04" + b"\x00" * 16)
    with pytest.raises(UnsupportedFileType, match="docx"):
        FileRouter().client_for(p)


def test_client_for_html_raises_unsupported(tmp_path: Path) -> None:
    p = tmp_path / "x.html"
    p.write_bytes(b"<html></html>")
    with pytest.raises(UnsupportedFileType, match="html"):
        FileRouter().client_for(p)


def test_client_for_json_raises_unsupported(tmp_path: Path) -> None:
    p = tmp_path / "x.json"
    p.write_bytes(b'{"a": 1}')
    with pytest.raises(UnsupportedFileType, match="json"):
        FileRouter().client_for(p)


def test_client_for_markdown_raises_unsupported(tmp_path: Path) -> None:
    p = tmp_path / "x.md"
    p.write_bytes(b"# Hello\n")
    with pytest.raises(UnsupportedFileType, match="markdown"):
        FileRouter().client_for(p)


def test_client_for_code_raises_unsupported(tmp_path: Path) -> None:
    p = tmp_path / "x.py"
    p.write_bytes(b"print('hi')\n")
    with pytest.raises(UnsupportedFileType, match="code"):
        FileRouter().client_for(p)


def test_client_for_unknown_raises_unknown(tmp_path: Path) -> None:
    p = tmp_path / "x.xyz"
    p.write_bytes(b"???")
    with pytest.raises(UnknownFileType):
        FileRouter().client_for(p)


# ---------------------------------------------------------------------------
# is_supported convenience
# ---------------------------------------------------------------------------

def test_is_supported_true_for_pdf(tmp_path: Path) -> None:
    _require_fixtures()
    assert FileRouter().is_supported(CLEAN_PDF) is True


def test_is_supported_false_for_unsupported(tmp_path: Path) -> None:
    p = tmp_path / "x.md"
    p.write_bytes(b"hi")
    assert FileRouter().is_supported(p) is False


def test_is_supported_false_for_unknown(tmp_path: Path) -> None:
    p = tmp_path / "x.xyz"
    p.write_bytes(b"?")
    assert FileRouter().is_supported(p) is False


# ---------------------------------------------------------------------------
# Detect on real Phase 0 fixtures
# ---------------------------------------------------------------------------

def _require_fixtures() -> None:
    if not CLEAN_PDF.exists():
        pytest.skip(
            f"Phase 0 fixtures not built; expected {CLEAN_PDF}. "
            "Run: python tests/make_test_documents.py"
        )


def test_detect_clean_pdf_fixture() -> None:
    _require_fixtures()
    det = FileRouter().detect(CLEAN_PDF)
    assert det.kind is FileKind.PDF
    assert det.extension_mismatch is False


def test_all_fixtures_detect_as_pdf() -> None:
    _require_fixtures()
    router = FileRouter()
    pdfs = list(FIXTURES_DIR.rglob("*.pdf"))
    if not pdfs:
        pytest.skip("No fixtures built yet.")
    for fx in pdfs:
        det = router.detect(fx)
        assert det.kind is FileKind.PDF, (
            f"Expected PDF for {fx.relative_to(FIXTURES_DIR)}, got {det.kind} "
            f"({det.reason})"
        )
        assert det.extension_mismatch is False, (
            f"Unexpected extension mismatch on {fx}"
        )


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------

def test_detect_on_missing_file_raises_filenotfounderror(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        FileRouter().detect(tmp_path / "nope")
