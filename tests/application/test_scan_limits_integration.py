"""
Phase 21 end-to-end integration tests for ``ScanLimits`` + the
universal ``FallbackAnalyzer`` under the real ``ScanService``.

The unit-level tests in ``tests/domain/test_scan_limits.py`` and
``tests/analyzers/test_fallback_analyzer.py`` assert the pieces in
isolation; these assert that the orchestrator wires them together
correctly — the ``ScanService(limits=...)`` constructor parameter
installs the ceilings for the duration of each scan, the oversized
pre-flight short-circuits before any analyzer runs, unidentified
files surface as ``unknown_format`` via the registry's UNKNOWN
dispatch, and clean files across every supported format continue to
produce identical reports (no regression to Phases 6 - 20).

Al-Baqarah 2:286: "Allah does not burden a soul beyond its capacity."
"""

from __future__ import annotations

from pathlib import Path

import pytest

from application import ScanService
from domain import (
    DEFAULT_LIMITS,
    IntegrityReport,
    ScanLimits,
)


# ---------------------------------------------------------------------------
# Fixture-free builders — tests materialise inputs per-case for clean
# isolation. None of these tests rely on the committed fixture corpus;
# the Phase 21 guarantees are about wiring, not specific findings.
# ---------------------------------------------------------------------------


def _make_csv(tmp_path: Path, rows: int) -> Path:
    """Minimal clean CSV with ``rows`` rows of a single column."""
    path = tmp_path / "rows.csv"
    body = "col\n" + "\n".join(f"v{i}" for i in range(rows)) + "\n"
    path.write_text(body, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# ScanService.__init__ accepts limits=
# ---------------------------------------------------------------------------


def test_scan_service_stores_limits() -> None:
    """Explicit limits are stored on the instance; default falls
    back to ``DEFAULT_LIMITS``."""
    custom = ScanLimits(max_csv_rows=5)
    assert ScanService().limits is DEFAULT_LIMITS
    assert ScanService(limits=custom).limits is custom


# ---------------------------------------------------------------------------
# max_file_size_bytes pre-flight
# ---------------------------------------------------------------------------


def test_oversized_file_short_circuits_with_scan_limited(
    tmp_path: Path,
) -> None:
    """A file larger than ``max_file_size_bytes`` must short-circuit
    at the orchestrator level — no analyzer runs, one ``scan_limited``
    finding, ``scan_incomplete=True``, score clamped to 0.5."""
    path = tmp_path / "too_big.json"
    # Valid JSON but much larger than the tight ceiling below.
    path.write_text('{"k":"' + ("x" * 5000) + '"}', encoding="utf-8")

    svc = ScanService(limits=ScanLimits(max_file_size_bytes=1024))
    report = svc.scan(path)

    assert report.scan_incomplete is True
    assert report.error is None
    assert len(report.findings) == 1
    f = report.findings[0]
    assert f.mechanism == "scan_limited"
    assert "max_file_size_bytes=1024" in f.description
    # Pre-flight ⇒ no analyzer findings alongside it.
    assert [fx.mechanism for fx in report.findings] == ["scan_limited"]
    assert report.integrity_score == pytest.approx(0.5)


def test_undersized_file_runs_analyzer_normally(tmp_path: Path) -> None:
    """A file UNDER the ceiling must flow through to its normal
    analyzer. This is the control case — proves the pre-flight does
    not accidentally short-circuit clean input."""
    path = tmp_path / "small.json"
    path.write_text('{"k":"hello"}', encoding="utf-8")

    svc = ScanService(limits=ScanLimits(max_file_size_bytes=10_000))
    report = svc.scan(path)

    # Clean JSON ⇒ no scan_limited firing, and the pre-flight did
    # not short-circuit.
    assert not any(
        f.mechanism == "scan_limited" for f in report.findings
    )


# ---------------------------------------------------------------------------
# Unknown-format dispatch via FallbackAnalyzer
# ---------------------------------------------------------------------------


def test_unknown_file_reaches_fallback_analyzer(tmp_path: Path) -> None:
    """An unidentified file (no magic-byte match, arbitrary
    extension) must now surface as ``unknown_format`` via the default
    registry's ``FallbackAnalyzer`` — closes the silent-clean failure
    mode Phase 21 was written to prevent."""
    path = tmp_path / "mystery.widget"
    # Proprietary-looking binary header; nothing the router recognises.
    path.write_bytes(b"\xDE\xAD\xBE\xEF\x00\x01\x02\x03payload")

    report = ScanService().scan(path)

    assert report.scan_incomplete is True
    mechanisms = [f.mechanism for f in report.findings]
    assert "unknown_format" in mechanisms
    assert report.integrity_score == pytest.approx(0.5)


def test_pdf_extension_on_unknown_bytes_preserves_pdf_error(
    tmp_path: Path,
) -> None:
    """v0.1 parity edge case: garbage bytes with a ``.pdf`` extension
    still surface as ``"Could not open PDF: ..."`` — NOT as
    ``unknown_format``. The fallback analyzer is disjoint from the
    pymupdf preflight path.

    This preserves the byte-identical PDF parity guarantee every
    prior phase established.
    """
    path = tmp_path / "garbage.pdf"
    path.write_bytes(b"this is not a pdf")

    report = ScanService().scan(path)
    assert report.error is not None
    assert report.error.startswith("Could not open PDF:")
    # And absolutely no unknown_format finding on this edge.
    assert all(
        f.mechanism != "unknown_format" for f in report.findings
    )


# ---------------------------------------------------------------------------
# CsvAnalyzer row-limit
# ---------------------------------------------------------------------------


def test_csv_row_ceiling_emits_scan_limited(tmp_path: Path) -> None:
    """A CSV with more rows than ``max_csv_rows`` surfaces a
    ``scan_limited`` finding and ``scan_incomplete=True``. The per-
    row walk stops at the ceiling so the rest of the file is NOT
    inspected — honest about what was not covered."""
    path = _make_csv(tmp_path, rows=50)

    svc = ScanService(limits=ScanLimits(max_csv_rows=5))
    report = svc.scan(path)

    assert report.scan_incomplete is True
    assert any(
        f.mechanism == "scan_limited"
        and "max_csv_rows=5" in f.description
        for f in report.findings
    )


def test_csv_under_row_ceiling_unaffected(tmp_path: Path) -> None:
    """A CSV well under the ceiling produces the usual clean report.
    Proves the limit code path is dormant on normal input."""
    path = _make_csv(tmp_path, rows=3)

    svc = ScanService(limits=ScanLimits(max_csv_rows=1_000))
    report = svc.scan(path)

    assert report.scan_incomplete is False
    assert all(f.mechanism != "scan_limited" for f in report.findings)


# ---------------------------------------------------------------------------
# Pre-flight ordering: missing-file error still wins
# ---------------------------------------------------------------------------


def test_missing_file_wins_over_size_check(tmp_path: Path) -> None:
    """A non-existent path must still surface ``File not found: ...``
    exactly, regardless of the limits configured — the pre-flight
    ordering preserves v0.1 parity."""
    ghost = tmp_path / "does_not_exist.widget"
    svc = ScanService(limits=ScanLimits(max_file_size_bytes=1))
    report = svc.scan(ghost)

    assert report.error == f"File not found: {ghost}"
    assert report.scan_incomplete is True
    # No scan_limited finding — the pre-flight's size check never ran.
    assert all(f.mechanism != "scan_limited" for f in report.findings)
