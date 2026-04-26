"""
Tests for analyzers.base.BaseAnalyzer.

Coverage targets:
  * ABC contract — cannot instantiate without overriding scan()
  * __init_subclass__ validation for name / error_prefix / source_layer
  * Intermediate abstract subclasses are exempt from that validation
  * Helper methods _empty_report and _scan_error_report produce the
    canonical shapes
  * scan_error attribution respects the analyzer's source_layer, even
    though the mechanism itself defaults to batin
"""

from __future__ import annotations

from pathlib import Path

import pytest

from analyzers.base import BaseAnalyzer
from domain import IntegrityReport


# ---------------------------------------------------------------------------
# Minimal valid subclass for happy-path tests
# ---------------------------------------------------------------------------

class _OkAnalyzer(BaseAnalyzer):
    name = "ok"
    error_prefix = "Ok error"
    source_layer = "zahir"

    def scan(self, pdf_path: Path) -> IntegrityReport:
        return self._empty_report(pdf_path)


# ---------------------------------------------------------------------------
# ABC contract
# ---------------------------------------------------------------------------

def test_base_analyzer_cannot_be_instantiated_directly() -> None:
    """ABC semantics — .scan is abstract, raw BaseAnalyzer cannot be built."""
    with pytest.raises(TypeError):
        BaseAnalyzer()  # type: ignore[abstract]


def test_concrete_subclass_can_be_instantiated() -> None:
    analyzer = _OkAnalyzer()
    assert analyzer.name == "ok"
    assert analyzer.source_layer == "zahir"
    assert "ok" in repr(analyzer)


# ---------------------------------------------------------------------------
# __init_subclass__ validation
# ---------------------------------------------------------------------------

def test_concrete_subclass_without_name_is_rejected() -> None:
    with pytest.raises(TypeError, match="name"):
        class _NoName(BaseAnalyzer):
            # missing .name
            error_prefix = "x"
            source_layer = "zahir"

            def scan(self, pdf_path: Path) -> IntegrityReport:
                return self._empty_report(pdf_path)


def test_concrete_subclass_with_invalid_source_layer_is_rejected() -> None:
    with pytest.raises(TypeError, match="source_layer"):
        class _BadLayer(BaseAnalyzer):
            name = "bad"
            error_prefix = "x"
            source_layer = "other"  # type: ignore[assignment]

            def scan(self, pdf_path: Path) -> IntegrityReport:
                return self._empty_report(pdf_path)


def test_concrete_subclass_with_empty_error_prefix_is_rejected() -> None:
    with pytest.raises(TypeError, match="error_prefix"):
        class _NoPrefix(BaseAnalyzer):
            name = "x"
            error_prefix = ""
            source_layer = "batin"

            def scan(self, pdf_path: Path) -> IntegrityReport:
                return self._empty_report(pdf_path)


def test_intermediate_abstract_subclass_is_exempt_from_validation() -> None:
    """A subclass that re-declares .scan as abstract is still abstract
    and must not trigger name/source_layer validation — only the
    eventual concrete leaf must satisfy it."""
    from abc import abstractmethod

    class _Intermediate(BaseAnalyzer):
        # no name, no source_layer override — fine because still abstract
        @abstractmethod
        def scan(self, pdf_path: Path) -> IntegrityReport:  # type: ignore[override]
            ...

    # ...and the concrete leaf still has to satisfy validation.
    class _Leaf(_Intermediate):
        name = "leaf"
        error_prefix = "Leaf error"
        source_layer = "batin"

        def scan(self, pdf_path: Path) -> IntegrityReport:
            return self._empty_report(pdf_path)

    assert _Leaf().name == "leaf"


# ---------------------------------------------------------------------------
# Helper methods
# ---------------------------------------------------------------------------

def test_empty_report_shape(tmp_path: Path) -> None:
    pdf = tmp_path / "x.pdf"
    pdf.touch()
    report = _OkAnalyzer()._empty_report(pdf)
    assert isinstance(report, IntegrityReport)
    assert report.file_path == str(pdf)
    assert report.integrity_score == 1.0
    assert report.findings == []
    assert report.error is None
    assert report.scan_incomplete is False


def test_scan_error_report_shape(tmp_path: Path) -> None:
    pdf = tmp_path / "x.pdf"
    pdf.touch()
    report = _OkAnalyzer()._scan_error_report(pdf, "pymupdf choked")

    assert isinstance(report, IntegrityReport)
    assert report.file_path == str(pdf)
    assert report.scan_incomplete is True
    assert report.error == "Ok error: pymupdf choked"
    assert len(report.findings) == 1

    finding = report.findings[0]
    assert finding.mechanism == "scan_error"
    assert finding.tier == 3
    assert finding.confidence == 1.0
    # scan_error severity is 0.00 — reported but non-deducting.
    assert finding.severity == 0.0
    # Critically: source_layer is attributed to the analyzer's declared
    # layer (zahir here), NOT the mechanism's default (batin).
    assert finding.source_layer == "zahir"
    assert finding.location == "analyzer:ok"


def test_scan_error_attributes_batin_for_batin_analyzer(tmp_path: Path) -> None:
    class _BatinAnalyzer(BaseAnalyzer):
        name = "batin_ok"
        error_prefix = "Batin error"
        source_layer = "batin"

        def scan(self, pdf_path: Path) -> IntegrityReport:
            return self._empty_report(pdf_path)

    pdf = tmp_path / "x.pdf"
    pdf.touch()
    report = _BatinAnalyzer()._scan_error_report(pdf, "boom")
    assert report.findings[0].source_layer == "batin"


def test_scan_error_report_custom_location(tmp_path: Path) -> None:
    pdf = tmp_path / "x.pdf"
    pdf.touch()
    report = _OkAnalyzer()._scan_error_report(
        pdf, "boom", location="page 5, font 'Fadv'",
    )
    assert report.findings[0].location == "page 5, font 'Fadv'"


def test_repr_is_useful() -> None:
    assert repr(_OkAnalyzer()) == "_OkAnalyzer(name='ok', source_layer='zahir')"
