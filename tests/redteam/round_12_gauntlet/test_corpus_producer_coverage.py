"""Round 12 MEDIUM 2 closure: producer-family corpus coverage.

Per v3 section 15.1 third failure mode (coverage narrowing): the
existing fixture corpus under tests/fixtures/ is produced by
pymupdf via make_test_documents.py. The analyzer reads with pypdf.
Both share library lineage; the fixture cannot exercise shapes
its own producer cannot represent. Round 12 (Bilal's 2026-05-06
incident report) surfaced two false positives that lived exactly
in this blind spot - the analyzer fired on shapes pymupdf does
not emit (LibreOffice destination-array OpenAction, pdfTeX
Computer Modern ToUnicode CMap).

This test asserts the corpus contains at least one fixture from
each of three real-world producer families: pymupdf (legacy
fixtures, retained as historical baseline), pdfTeX (academic /
technical PDFs), and LibreOffice (office traffic). A future
addition or regression that narrows the producer set fails this
test, surfacing the gap structurally rather than waiting for the
next manual incident report.
"""
from __future__ import annotations
from pathlib import Path
import pypdf
import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
ROUND_12_DIR = Path(__file__).parent
LEGACY_FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"


def _producer(pdf_path: Path) -> str:
    try:
        r = pypdf.PdfReader(pdf_path)
        return str(r.metadata.get("/Producer", ""))
    except Exception:
        return ""


def _producer_family(producer: str) -> str:
    """Categorise a /Producer string into a producer family."""
    if not producer:
        return "unknown"
    p = producer.lower()
    if any(s in producer for s in ("pdfTeX", "XeTeX", "LuaTeX", "dvips", "dvipdfm")):
        return "tex"
    if "libreoffice" in p or "openoffice" in p:
        return "libreoffice"
    if "pymupdf" in p or "mupdf" in p:
        return "pymupdf"
    if "microsoft word" in p or "word" in p and "office" in p:
        return "word"
    if "adobe" in p or "acrobat" in p:
        return "adobe"
    if "ghostscript" in p:
        return "ghostscript"
    return "other"


def _all_pdf_fixtures() -> list[Path]:
    """All PDFs in either the legacy corpus or Round 12 corpus."""
    out: list[Path] = []
    if LEGACY_FIXTURES_DIR.exists():
        out.extend(LEGACY_FIXTURES_DIR.rglob("*.pdf"))
    out.extend(ROUND_12_DIR.rglob("*.pdf"))
    return sorted(out)


def test_corpus_covers_pymupdf_producer_family() -> None:
    """Legacy baseline: at least one pymupdf-produced fixture must
    exist. This is the historical reference; removing all of them
    would drop the byte-parity baseline against bayyinah_v0."""
    pymupdf_fixtures = [
        f for f in _all_pdf_fixtures()
        if _producer_family(_producer(f)) == "pymupdf"
    ]
    assert pymupdf_fixtures, (
        "No pymupdf-produced fixture present; the byte-parity "
        "baseline against bayyinah_v0 depends on at least one"
    )


def test_corpus_covers_tex_producer_family() -> None:
    """Round 12 closure: at least one pdfTeX / XeTeX / LuaTeX
    fixture must exist. Round 12 surfaced false positives the
    pymupdf-only corpus could not reproduce."""
    tex_fixtures = [
        f for f in _all_pdf_fixtures()
        if _producer_family(_producer(f)) == "tex"
    ]
    assert tex_fixtures, (
        "No TeX-stack-produced fixture present; the corpus cannot "
        "exercise shapes only emitted by pdfTeX / XeTeX / LuaTeX. "
        "Add a fixture to tests/redteam/round_12_gauntlet/ via the "
        "build_clean_pdftex_*.py builders."
    )


def test_corpus_covers_libreoffice_producer_family() -> None:
    """Round 12 closure: at least one LibreOffice-produced fixture
    must exist (covers the destination-array OpenAction shape and
    related office-traffic patterns)."""
    libreoffice_fixtures = [
        f for f in _all_pdf_fixtures()
        if _producer_family(_producer(f)) == "libreoffice"
    ]
    assert libreoffice_fixtures, (
        "No LibreOffice-produced fixture present; the corpus cannot "
        "exercise shapes only emitted by LibreOffice (destination-"
        "array OpenAction, native Writer export). Add a fixture to "
        "tests/redteam/round_12_gauntlet/ via "
        "build_clean_libreoffice_*.py or build_libreoffice_writer_native.py."
    )
