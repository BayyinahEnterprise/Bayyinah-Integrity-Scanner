"""
Bayyinah infrastructure layer — adapters to the outside world.

This package contains every piece of Bayyinah that talks to something
Python itself does not: parser libraries (pypdf, pymupdf), the
filesystem, the terminal. Domain and analyzer layers above call *in*
to infrastructure through small, explicit contracts; infrastructure
does not call up into them.

Phase 3 of the Al-Baqarah refactor. Additive-only: ``bayyinah_v0`` and
``bayyinah_v0_1`` continue to own their own parser plumbing until
later phases migrate the pipeline onto these adapters.

Structural contents:

    PDFClient              — lazy pypdf / pymupdf handle, cached once
                             per file, context-manager safe.
    FileRouter             — magic-byte + extension file-type detection
                             with polyglot (extension/content mismatch)
                             surfacing. Dispatches to the right client.
    FileKind / UnsupportedFileType / UnknownFileType
                           — router domain types, re-exported so
                             callers do not need to know the module
                             layout.
    ReportFormatter        — abstract contract for rendering an
                             IntegrityReport to a string.
    TerminalReportFormatter / JsonReportFormatter / PlainLanguageFormatter
                           — the three concrete formatters that ship
                             in Phase 3.
    FormatterRegistry      — name-keyed registry, same shape as
                             ``AnalyzerRegistry``.
"""

from __future__ import annotations

from infrastructure.file_router import (
    FileKind,
    FileRouter,
    FileTypeDetection,
    UnknownFileType,
    UnsupportedFileType,
)
from infrastructure.pdf_client import PDFClient
from infrastructure.report_formatter import (
    FormatterRegistrationError,
    FormatterRegistry,
    JsonReportFormatter,
    PlainLanguageFormatter,
    ReportFormatter,
    TerminalReportFormatter,
    default_formatter_registry,
    plain_language_summary,
    registered,
)

__all__ = [
    # PDF client
    "PDFClient",
    # File router
    "FileRouter",
    "FileKind",
    "FileTypeDetection",
    "UnsupportedFileType",
    "UnknownFileType",
    # Formatters
    "ReportFormatter",
    "TerminalReportFormatter",
    "JsonReportFormatter",
    "PlainLanguageFormatter",
    "FormatterRegistry",
    "FormatterRegistrationError",
    "default_formatter_registry",
    "plain_language_summary",
    "registered",
]
