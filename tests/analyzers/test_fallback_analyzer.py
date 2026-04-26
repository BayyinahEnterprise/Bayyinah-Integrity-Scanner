"""
Tests for ``analyzers.fallback_analyzer.FallbackAnalyzer`` — the Phase 21
universal witness of last resort (Al-Baqarah 2:143).

The guarantee these tests assert is the one the scanner was missing
before Phase 21: a file whose type we could not identify never slips
through as silent-clean. Every such file surfaces as
``unknown_format`` with enough forensic metadata (magic bytes,
declared extension, size, head-preview in both hex and printable
ASCII) for the reader to begin their own classification, and the
report is marked ``scan_incomplete=True`` so the 0.5 clamp applies.

Parallels ``tests/analyzers/test_text_file_analyzer.py`` in shape —
contract assertions, then one targeted test per code path in ``scan``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from analyzers import FallbackAnalyzer
from analyzers.base import BaseAnalyzer
from domain import (
    DEFAULT_LIMITS,
    IntegrityReport,
    ScanLimits,
    limits_context,
)
from infrastructure.file_router import FileKind


# ---------------------------------------------------------------------------
# Contract
# ---------------------------------------------------------------------------


def test_is_base_analyzer_subclass() -> None:
    assert issubclass(FallbackAnalyzer, BaseAnalyzer)


def test_class_attributes() -> None:
    assert FallbackAnalyzer.name == "fallback"
    assert FallbackAnalyzer.error_prefix == "Fallback scan error"
    assert FallbackAnalyzer.source_layer == "batin"


def test_supported_kinds_is_unknown_only() -> None:
    """The fallback analyzer MUST declare only ``FileKind.UNKNOWN``.

    This is the single guarantee that keeps it from firing on any
    identified format — every other analyzer's ``supported_kinds``
    excludes ``UNKNOWN``, and ``FallbackAnalyzer.supported_kinds``
    excludes everything else. The registry's ``scan_all(kind=...)``
    filter therefore routes the fallback exclusively to unidentified
    inputs, preserving PDF / DOCX / HTML / XLSX / PPTX / EML / CSV /
    JSON / image / text parity by construction.
    """
    assert FallbackAnalyzer.supported_kinds == frozenset({FileKind.UNKNOWN})


# ---------------------------------------------------------------------------
# Missing-file path
# ---------------------------------------------------------------------------


def test_missing_file_produces_scan_error(tmp_path: Path) -> None:
    """A path that does not exist surfaces as ``scan_error`` — consistent
    with every other analyzer's missing-file semantics."""
    ghost = tmp_path / "does_not_exist.xyz"
    report = FallbackAnalyzer().scan(ghost)

    assert isinstance(report, IntegrityReport)
    assert report.scan_incomplete is True
    assert len(report.findings) == 1
    assert report.findings[0].mechanism == "scan_error"


# ---------------------------------------------------------------------------
# Unknown-format happy path
# ---------------------------------------------------------------------------


def test_empty_file_produces_unknown_format_finding(tmp_path: Path) -> None:
    """An empty file (no bytes at all) is still unknown — emit the
    finding with the size-zero metadata so the reader can see that's
    exactly what the file was."""
    path = tmp_path / "empty.bin"
    path.write_bytes(b"")

    report = FallbackAnalyzer().scan(path)
    assert report.scan_incomplete is True
    assert len(report.findings) == 1
    f = report.findings[0]
    assert f.mechanism == "unknown_format"
    assert f.tier == 3
    assert f.confidence == 1.0
    assert f.source_layer == "batin"
    assert "size_bytes=0" in f.description
    assert "extension='.bin'" in f.description


def test_known_bytes_produces_metadata_fields(tmp_path: Path) -> None:
    """Arbitrary proprietary bytes: every metadata field in the finding
    must be populated and accurate."""
    payload = b"\xDE\xAD\xBE\xEFhello world, this is plainly visible.\n"
    path = tmp_path / "proprietary.widget"
    path.write_bytes(payload)

    report = FallbackAnalyzer().scan(path)
    assert report.scan_incomplete is True
    assert len(report.findings) == 1
    f = report.findings[0]
    assert f.mechanism == "unknown_format"
    # magic_bytes_hex: first 16 bytes of the payload, hex-encoded.
    expected_magic = payload[:16].hex()
    assert expected_magic in f.description
    assert expected_magic in f.concealed
    # Declared extension surfaces both in surface and description.
    assert "'.widget'" in f.description
    assert ".widget" in f.surface
    # Printable-ASCII preview of the payload — non-printables become '.'.
    assert "hello world, this is plainly visible." in f.concealed
    # Size_bytes field accurate.
    assert f"size_bytes={len(payload)}" in f.description
    assert f"file size {len(payload)} bytes" in f.surface


def test_file_without_extension_reports_none(tmp_path: Path) -> None:
    path = tmp_path / "no_extension_here"
    path.write_bytes(b"some bytes")

    report = FallbackAnalyzer().scan(path)
    assert len(report.findings) == 1
    f = report.findings[0]
    # No extension renders as the literal '(none)' sentinel so the
    # reader sees explicitly that no extension was declared (not that
    # the extension field is simply missing from the output).
    assert "'(none)'" in f.description


def test_head_preview_truncated_at_512_bytes(tmp_path: Path) -> None:
    """Files larger than the head-preview cut-off must still emit one
    finding with exactly 512 bytes of preview."""
    payload = b"A" * 2000
    path = tmp_path / "bigger.xyz"
    path.write_bytes(payload)

    report = FallbackAnalyzer().scan(path)
    f = report.findings[0]
    assert "head_preview_bytes=512" in f.description
    # ASCII preview should only contain 512 'A' characters (not 2000).
    assert "A" * 512 in f.concealed
    assert "A" * 513 not in f.concealed


# ---------------------------------------------------------------------------
# Oversized-file → scan_limited
# ---------------------------------------------------------------------------


def test_oversized_file_emits_scan_limited(tmp_path: Path) -> None:
    """A file past ``max_file_size_bytes`` short-circuits with a
    ``scan_limited`` finding — the analyzer never reads the head
    preview, so the scanner can't be used as a DoS vector against
    pathologically-large files."""
    path = tmp_path / "big.xyz"
    path.write_bytes(b"x" * 5000)

    with limits_context(ScanLimits(max_file_size_bytes=1024)):
        report = FallbackAnalyzer().scan(path)

    assert report.scan_incomplete is True
    assert len(report.findings) == 1
    f = report.findings[0]
    assert f.mechanism == "scan_limited"
    assert f.tier == 3
    assert "5000 bytes" in f.description
    assert "max_file_size_bytes=1024" in f.description


def test_scan_incomplete_clamps_the_score(tmp_path: Path) -> None:
    """Because every FallbackAnalyzer report is scan_incomplete, the
    score is clamped to the 0.5 ``SCAN_INCOMPLETE_CLAMP``."""
    path = tmp_path / "unknown.blob"
    path.write_bytes(b"whatever")

    report = FallbackAnalyzer().scan(path)
    # SCAN_INCOMPLETE_CLAMP is 0.5 — the finding is severity 0.0
    # (non-deducting), so the raw score is 1.0 and the clamp brings
    # it to 0.5.
    assert report.integrity_score == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Default limits survive outside a context
# ---------------------------------------------------------------------------


def test_default_limits_used_outside_context(tmp_path: Path) -> None:
    """Outside ``limits_context``, ``get_current_limits`` must fall
    back to ``DEFAULT_LIMITS`` — so importing and calling an analyzer
    directly in tests / notebooks works without needing to scope a
    context manager."""
    path = tmp_path / "tiny.bin"
    path.write_bytes(b"abc")

    # 3 bytes is far below DEFAULT_LIMITS.max_file_size_bytes (256 MB)
    # so the oversized path must NOT trigger; we should get the
    # standard unknown_format finding.
    assert DEFAULT_LIMITS.max_file_size_bytes > 3

    report = FallbackAnalyzer().scan(path)
    assert len(report.findings) == 1
    assert report.findings[0].mechanism == "unknown_format"
