"""
Bayyinah — the public Python API (Al-Baqarah 2:204).

    وَمِنَ النَّاسِ مَن يُعْجِبُكَ قَوْلُهُ فِي الْحَيَاةِ الدُّنْيَا وَيُشْهِدُ اللَّهَ عَلَىٰ مَا فِي قَلْبِهِ
    وَهُوَ أَلَدُّ الْخِصَامِ

    "And of the people is he whose speech pleases you in worldly life,
    and he calls Allah to witness as to what is in his heart, yet he is
    the fiercest of opponents."

The architectural reading: a document may speak pleasingly on the
surface while something quite different lives inside. That gap is the
whole subject of this tool. Bayyinah renders the invisible visible and
lets the reader perform the recognition — it makes no moral verdict of
its own.

This package is the surface the world sees. It re-exports exactly the
pieces a caller needs to scan a file, consume the report, and render
it — nothing more. The internal module layout (``domain``,
``infrastructure``, ``analyzers``, ``application``) is the
implementation; the top-level ``bayyinah`` namespace is the contract.

Usage — the scan::

    >>> from bayyinah import scan_pdf
    >>> report = scan_pdf("document.pdf")
    >>> report.integrity_score
    0.873
    >>> [f.mechanism for f in report.findings]
    ['additional_actions']

Usage — the formatter::

    >>> from bayyinah import scan_pdf, format_text_report
    >>> print(format_text_report(scan_pdf("document.pdf")))

Usage — a custom analyzer set::

    >>> from bayyinah import ScanService, AnalyzerRegistry
    >>> from bayyinah.analyzers import ZahirTextAnalyzer
    >>> registry = AnalyzerRegistry()
    >>> registry.register(ZahirTextAnalyzer)
    >>> report = ScanService(registry=registry).scan("document.pdf")

Semantics guarantee: ``bayyinah.scan_pdf`` is byte-identical to
``bayyinah_v0.scan_pdf`` on every Phase 0 fixture — same findings,
same score, same error string, same scan_incomplete flag. The modular
refactor was additive: the reference implementation is preserved
unchanged at ``bayyinah_v0.py`` for comparison, and this package
delegates all work to the refactored ``application.ScanService``.

Reference: Munafiq Protocol §9 — performed-alignment detection at the
input layer. DOI: 10.5281/zenodo.19677111
"""

from __future__ import annotations

from pathlib import Path

from application import ScanService, default_pdf_registry, default_registry
from analyzers import (
    AnalyzerRegistrationError,
    AnalyzerRegistry,
    AudioAnalyzer,
    BaseAnalyzer,
    BatinObjectAnalyzer,
    CrossModalCorrelationEngine,
    CsvAnalyzer,
    DocxAnalyzer,
    EmlAnalyzer,
    FallbackAnalyzer,
    HtmlAnalyzer,
    PptxAnalyzer,
    VideoAnalyzer,
    XlsxAnalyzer,
    ZahirTextAnalyzer,
)
from domain import (
    BayyinahError,
    DEFAULT_LIMITS,
    Finding,
    IntegrityReport,
    InvalidFindingError,
    MECHANISM_REGISTRY,
    PDFParseError,
    ScanError,
    ScanLimits,
    SourceLayer,
    TOOL_NAME,
    TOOL_VERSION,
    Verdict,
    VERDICT_DISCLAIMER,
    VERDICT_MUGHLAQ,
    VERDICT_MUKHFI,
    VERDICT_MUNAFIQ,
    VERDICT_MUSHTABIH,
    VERDICT_SAHIH,
    apply_scan_incomplete_clamp,
    compute_muwazana_score,
    get_current_limits,
    limits_context,
    set_current_limits,
    tamyiz_verdict,
)
from infrastructure import (
    FileKind,
    FileRouter,
    FileTypeDetection,
    JsonReportFormatter,
    PDFClient,
    PlainLanguageFormatter,
    ReportFormatter,
    TerminalReportFormatter,
    UnknownFileType,
    UnsupportedFileType,
    plain_language_summary,
)


# ---------------------------------------------------------------------------
# Public version — keep in sync with [project.version] in pyproject.toml.
# ---------------------------------------------------------------------------

__version__ = "1.1.5"


# ---------------------------------------------------------------------------
# scan_pdf — the public entry point
# ---------------------------------------------------------------------------

def scan_pdf(pdf_path: Path | str) -> IntegrityReport:
    """Scan a single PDF for integrity violations.

    This is the canonical public entry point. It accepts a ``Path`` or a
    string and returns an ``IntegrityReport`` containing every finding
    from every registered analyzer, the merged APS-continuous score,
    and the scan-completeness flag.

    The semantics are byte-identical to ``bayyinah_v0.scan_pdf`` on
    every Phase 0 fixture:

        * Missing file   → error="File not found: <path>",
                           integrity_score=0.0, scan_incomplete=True.
        * Unopenable PDF → error="Could not open PDF: <pymupdf-message>",
                           integrity_score=0.0, scan_incomplete=True.
        * Clean file     → zero findings, integrity_score=1.0.
        * Findings       → per-analyzer findings concatenated in
                           registration order (text then object), with
                           a muwazana score of
                           ``clamp(1.0 - Σ(sev × conf), 0, 1)``. The
                           score is clamped to 0.5 whenever
                           ``scan_incomplete`` is set.

    Examples
    --------
    >>> from bayyinah import scan_pdf
    >>> r = scan_pdf("tests/fixtures/clean.pdf")
    >>> r.integrity_score
    1.0
    >>> r.findings
    []
    """
    return ScanService().scan(Path(pdf_path))


# ---------------------------------------------------------------------------
# scan_file — the format-agnostic public entry point
# ---------------------------------------------------------------------------

def scan_file(
    file_path: Path | str,
    *,
    mode: str = "forensic",
) -> IntegrityReport:
    """Scan a single file of any supported format for integrity violations.

    Format-agnostic counterpart to :func:`scan_pdf`. Dispatches to the
    default :class:`ScanService`, which routes the file through the
    :class:`FileRouter` to pick the correct analyzer set for the detected
    ``FileKind`` (PDF, DOCX, HTML, XLSX, PPTX, EML, CSV, JSON, images,
    SVG, markdown / code / plain text). Files whose bytes no magic prefix
    recognises and whose extension no map entry covers are handled by
    :class:`FallbackAnalyzer` — they surface an ``unknown_format``
    finding rather than slipping through silent-clean.

    This is the recommended top-level entry point for Bayyinah 1.0.
    :func:`scan_pdf` is preserved as a backward-compatible alias for
    callers who pinned to the PDF-only entry point; internally it
    delegates to the same :class:`ScanService` and is byte-identical.

    The ``mode`` parameter (v1.1.4) accepts ``"forensic"`` (default,
    every analyzer runs to completion) or ``"production"`` (early
    termination on Tier 1 high-confidence findings; queued for full
    pass-by-pass dispatch in v1.1.5). Forensic is the byte-parity-
    preserving default for backward compatibility.

    Examples
    --------
    >>> from bayyinah import scan_file
    >>> r = scan_file("contract.pdf")
    >>> r.integrity_score
    1.0
    >>> r = scan_file("invoice.docx")      # any supported format
    >>> r = scan_file("unknown.widget")    # falls back to FallbackAnalyzer
    >>> r = scan_file("memo.pdf", mode="production")  # production mode

    Semantics match :func:`scan_pdf` for PDF inputs exactly; non-PDF
    inputs return the composed :class:`IntegrityReport` from the
    analyzers registered for that :class:`FileKind`.
    """
    return ScanService().scan(Path(file_path), mode=mode)


# ---------------------------------------------------------------------------
# format_text_report — convenience formatter (mirrors v0/v0.1 surface)
# ---------------------------------------------------------------------------

def format_text_report(report: IntegrityReport) -> str:
    """Render an IntegrityReport as a human-readable terminal string.

    Thin wrapper over ``TerminalReportFormatter``. Byte-identical to
    ``bayyinah_v0_1.format_text_report`` output.
    """
    return TerminalReportFormatter().format(report)


__all__ = [
    # Version
    "__version__",
    # Primary entry points
    "scan_file",
    "scan_pdf",
    "format_text_report",
    # Orchestrator + factory
    "ScanService",
    "default_pdf_registry",
    "default_registry",
    # Analyzer surface
    "AnalyzerRegistry",
    "AnalyzerRegistrationError",
    "BaseAnalyzer",
    "ZahirTextAnalyzer",
    "BatinObjectAnalyzer",
    "DocxAnalyzer",
    "HtmlAnalyzer",
    "XlsxAnalyzer",
    "PptxAnalyzer",
    "EmlAnalyzer",
    "CsvAnalyzer",
    # Phase 21 — the universal witness of last resort.
    "FallbackAnalyzer",
    # Phase 24 — video-container decomposition (MP4/MOV/WEBM/MKV).
    "VideoAnalyzer",
    # Phase 24 — audio-container decomposition (MP3/WAV/FLAC/M4A/OGG).
    "AudioAnalyzer",
    # Phase 25+ — cross-modal correlation post-processor.
    "CrossModalCorrelationEngine",
    # Infrastructure surface
    "PDFClient",
    "FileRouter",
    "FileKind",
    "FileTypeDetection",
    "UnsupportedFileType",
    "UnknownFileType",
    "ReportFormatter",
    "TerminalReportFormatter",
    "JsonReportFormatter",
    "PlainLanguageFormatter",
    "plain_language_summary",
    # Domain surface
    "Finding",
    "IntegrityReport",
    "SourceLayer",
    "compute_muwazana_score",
    "tamyiz_verdict",
    "apply_scan_incomplete_clamp",
    "Verdict",
    "VERDICT_DISCLAIMER",
    "VERDICT_SAHIH",
    "VERDICT_MUSHTABIH",
    "VERDICT_MUKHFI",
    "VERDICT_MUNAFIQ",
    "VERDICT_MUGHLAQ",
    "MECHANISM_REGISTRY",
    "TOOL_NAME",
    "TOOL_VERSION",
    # Phase 21 — configurable safety limits.
    "ScanLimits",
    "DEFAULT_LIMITS",
    "get_current_limits",
    "set_current_limits",
    "limits_context",
    # Exceptions
    "BayyinahError",
    "PDFParseError",
    "InvalidFindingError",
    "ScanError",
]
