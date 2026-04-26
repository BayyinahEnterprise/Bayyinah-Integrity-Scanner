"""Tests for domain.exceptions — the Bayyinah exception hierarchy."""

from __future__ import annotations

import pytest

from domain.exceptions import (
    BayyinahError,
    InvalidFindingError,
    PDFParseError,
    ScanError,
)


def test_bayyinah_error_is_an_exception() -> None:
    assert issubclass(BayyinahError, Exception)


def test_pdf_parse_error_is_a_bayyinah_error() -> None:
    assert issubclass(PDFParseError, BayyinahError)


def test_scan_error_is_a_bayyinah_error() -> None:
    assert issubclass(ScanError, BayyinahError)


def test_invalid_finding_error_is_a_bayyinah_error_and_value_error() -> None:
    """Multiple inheritance is intentional so callers that handle either
    ``BayyinahError`` (our hierarchy) or ``ValueError`` (generic domain
    bug) both catch invalid Finding construction."""
    assert issubclass(InvalidFindingError, BayyinahError)
    assert issubclass(InvalidFindingError, ValueError)


def test_scan_error_carries_optional_layer_attribute() -> None:
    exc = ScanError("text extraction failed", layer="zahir")
    assert exc.layer == "zahir"
    assert str(exc) == "text extraction failed"


def test_scan_error_default_layer_is_none() -> None:
    assert ScanError("bare").layer is None


def test_raising_and_catching_via_root() -> None:
    """One ``except BayyinahError`` catches every subclass."""
    for cls in (PDFParseError, ScanError, InvalidFindingError):
        with pytest.raises(BayyinahError):
            raise cls("boom")
