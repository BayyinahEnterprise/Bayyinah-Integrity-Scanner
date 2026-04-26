"""
Bayyinah domain exceptions.

These types are the contract the domain layer uses to signal failure.
Infrastructure adapters (pypdf, pymupdf) raise library-specific
exceptions; analyzers catch those and re-raise a Bayyinah exception
that callers can handle without importing the underlying parser.

Design invariant: every exception here inherits from ``BayyinahError``,
so a single ``except BayyinahError`` at the edge catches anything the
domain layer can raise. Python's built-in exceptions (``TypeError``,
``ValueError``) still surface for real programming bugs — those should
not be silently swallowed.

Phase 1 introduces the hierarchy only. Nothing in ``bayyinah_v0.py`` or
``bayyinah_v0_1.py`` raises these yet; later phases will migrate the
scanner-side error paths onto this contract. Additive-only.
"""

from __future__ import annotations


class BayyinahError(Exception):
    """Root exception for every error raised from the Bayyinah domain.

    Callers that want to handle any Bayyinah-originated failure without
    caring which stage of the scan produced it should catch this type.
    Library errors from pypdf/pymupdf that we have not wrapped intentionally
    will NOT inherit from this — they are programming bugs we want to see.
    """


class PDFParseError(BayyinahError):
    """The file could not be opened, decoded, or parsed as a PDF.

    Raised when pypdf/pymupdf fail on the container (bad xref, truncated
    file, unsupported encryption). This is a structural failure — the
    scan cannot even begin.
    """


class ScanError(BayyinahError):
    """An analyzer could not complete its pass over the document.

    A ``ScanError`` is recoverable at the report level: the scanner
    records the failure as a ``scan_error`` finding, sets
    ``scan_incomplete = True``, and clamps the integrity score. The
    absence of findings from the incomplete region cannot be taken as
    evidence of cleanness — that is the whole point of the clamp.
    """

    def __init__(self, message: str, *, layer: str | None = None) -> None:
        super().__init__(message)
        self.layer = layer
        """Which source layer's analyzer failed — 'zahir' or 'batin' if
        known, else None. Lets report assembly attribute the scan_error
        correctly without re-inspecting the traceback."""


class InvalidFindingError(BayyinahError, ValueError):
    """A Finding was constructed with semantically invalid fields.

    Raised by ``Finding.__post_init__`` when confidence is out of range,
    tier is not 1/2/3, or source_layer is neither 'zahir' nor 'batin'.
    This is a programming error — inherits from ``ValueError`` so code
    that catches either type still catches it.
    """


__all__ = [
    "BayyinahError",
    "PDFParseError",
    "ScanError",
    "InvalidFindingError",
]
