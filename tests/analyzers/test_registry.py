"""
Tests for analyzers.registry.AnalyzerRegistry.

Coverage targets:
  * Registration accepts BaseAnalyzer subclasses; rejects non-classes,
    non-subclasses, empty names, and name collisions
  * Decorator usage (registry.register as a decorator, and the
    ``registered(registry)`` sugar)
  * Inspection surface: get/names/classes/__len__/__contains__/__iter__
  * Execution surface:
      - short-circuit on missing file
      - empty registry returns a clean report
      - findings concatenate in registration order
      - integrity score recomputed via compute_muwazana_score
      - scan_incomplete propagates from per-analyzer flags
      - unexpected analyzer exceptions are caught and rendered with
        error_prefix (v0.1-compatible "A; B" format)
      - one analyzer failing does not silence the others
      - scan_incomplete clamp applied at merged level
"""

from __future__ import annotations

from pathlib import Path

import pytest

from analyzers.base import BaseAnalyzer
from analyzers.registry import (
    AnalyzerRegistrationError,
    AnalyzerRegistry,
    registered,
)
from domain import (
    Finding,
    IntegrityReport,
    VERDICT_DISCLAIMER,
    compute_muwazana_score,
)
from domain.config import SCAN_INCOMPLETE_CLAMP


# ---------------------------------------------------------------------------
# Test fixtures — minimal analyzers
# ---------------------------------------------------------------------------

class _ZahirNoopAnalyzer(BaseAnalyzer):
    name = "zahir_noop"
    error_prefix = "Zahir noop error"
    source_layer = "zahir"

    def scan(self, pdf_path: Path) -> IntegrityReport:
        return self._empty_report(pdf_path)


class _BatinNoopAnalyzer(BaseAnalyzer):
    name = "batin_noop"
    error_prefix = "Batin noop error"
    source_layer = "batin"

    def scan(self, pdf_path: Path) -> IntegrityReport:
        return self._empty_report(pdf_path)


class _ZwspFireAnalyzer(BaseAnalyzer):
    """Always emits a single zero_width_chars finding."""
    name = "zwsp_fire"
    error_prefix = "Zwsp fire error"
    source_layer = "zahir"

    def scan(self, pdf_path: Path) -> IntegrityReport:
        r = self._empty_report(pdf_path)
        r.findings.append(Finding(
            mechanism="zero_width_chars", tier=2, confidence=1.0,
            description="zwsp detected", location="page 1",
        ))
        r.integrity_score = compute_muwazana_score(r.findings)
        return r


class _JsFireAnalyzer(BaseAnalyzer):
    """Always emits a javascript finding."""
    name = "js_fire"
    error_prefix = "Js fire error"
    source_layer = "batin"

    def scan(self, pdf_path: Path) -> IntegrityReport:
        r = self._empty_report(pdf_path)
        r.findings.append(Finding(
            mechanism="javascript", tier=1, confidence=1.0,
            description="/JS detected", location="catalog /OpenAction",
        ))
        r.integrity_score = compute_muwazana_score(r.findings)
        return r


class _RaisingAnalyzer(BaseAnalyzer):
    """Raises a RuntimeError mid-scan — tests registry's exception capture."""
    name = "raiser"
    error_prefix = "Raiser error"
    source_layer = "batin"

    def scan(self, pdf_path: Path) -> IntegrityReport:
        raise RuntimeError("analyzer exploded")


class _ExpectedErrorAnalyzer(BaseAnalyzer):
    """Returns a scan_error report via the helper — expected failure path."""
    name = "expected_error"
    error_prefix = "Expected error"
    source_layer = "zahir"

    def scan(self, pdf_path: Path) -> IntegrityReport:
        return self._scan_error_report(pdf_path, "couldn't open font stream")


@pytest.fixture
def pdf_path(tmp_path: Path) -> Path:
    p = tmp_path / "doc.pdf"
    p.write_bytes(b"%PDF-1.7\n%%EOF\n")  # content doesn't matter; file must exist
    return p


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def test_register_adds_class_to_registry() -> None:
    reg = AnalyzerRegistry()
    reg.register(_ZahirNoopAnalyzer)
    assert "zahir_noop" in reg
    assert reg.get("zahir_noop") is _ZahirNoopAnalyzer
    assert len(reg) == 1


def test_register_returns_class_so_it_can_be_used_as_decorator() -> None:
    reg = AnalyzerRegistry()

    @reg.register
    class _Dec(BaseAnalyzer):
        name = "dec_inline"
        error_prefix = "Dec error"
        source_layer = "zahir"

        def scan(self, pdf_path: Path) -> IntegrityReport:
            return self._empty_report(pdf_path)

    assert reg.get("dec_inline") is _Dec


def test_registered_sugar_decorator_binds_to_registry() -> None:
    reg = AnalyzerRegistry()

    @registered(reg)
    class _Dec2(BaseAnalyzer):
        name = "dec_sugar"
        error_prefix = "Dec2 error"
        source_layer = "batin"

        def scan(self, pdf_path: Path) -> IntegrityReport:
            return self._empty_report(pdf_path)

    assert reg.get("dec_sugar") is _Dec2


def test_register_rejects_non_class() -> None:
    reg = AnalyzerRegistry()
    with pytest.raises(AnalyzerRegistrationError):
        reg.register("not a class")  # type: ignore[arg-type]


def test_register_rejects_non_base_analyzer_class() -> None:
    reg = AnalyzerRegistry()

    class _NotAnAnalyzer:
        name = "x"

    with pytest.raises(AnalyzerRegistrationError):
        reg.register(_NotAnAnalyzer)  # type: ignore[arg-type]


def test_register_rejects_duplicate_name() -> None:
    reg = AnalyzerRegistry()
    reg.register(_ZahirNoopAnalyzer)

    class _Collide(BaseAnalyzer):
        name = "zahir_noop"  # collision
        error_prefix = "other"
        source_layer = "zahir"

        def scan(self, pdf_path: Path) -> IntegrityReport:
            return self._empty_report(pdf_path)

    with pytest.raises(AnalyzerRegistrationError, match="already registered"):
        reg.register(_Collide)


def test_unregister_removes_by_name() -> None:
    reg = AnalyzerRegistry()
    reg.register(_ZahirNoopAnalyzer)
    reg.unregister("zahir_noop")
    assert "zahir_noop" not in reg


def test_unregister_is_noop_for_unknown_name() -> None:
    reg = AnalyzerRegistry()
    reg.unregister("never_registered")  # must not raise
    assert len(reg) == 0


def test_clear_empties_registry() -> None:
    reg = AnalyzerRegistry()
    reg.register(_ZahirNoopAnalyzer)
    reg.register(_BatinNoopAnalyzer)
    reg.clear()
    assert len(reg) == 0


# ---------------------------------------------------------------------------
# Inspection
# ---------------------------------------------------------------------------

def test_get_raises_key_error_for_unknown_name() -> None:
    reg = AnalyzerRegistry()
    with pytest.raises(KeyError):
        reg.get("does_not_exist")


def test_names_preserves_registration_order() -> None:
    reg = AnalyzerRegistry()
    reg.register(_ZahirNoopAnalyzer)
    reg.register(_BatinNoopAnalyzer)
    reg.register(_ZwspFireAnalyzer)
    assert reg.names() == ["zahir_noop", "batin_noop", "zwsp_fire"]


def test_classes_preserves_registration_order() -> None:
    reg = AnalyzerRegistry()
    reg.register(_ZahirNoopAnalyzer)
    reg.register(_BatinNoopAnalyzer)
    assert reg.classes() == [_ZahirNoopAnalyzer, _BatinNoopAnalyzer]


def test_iter_yields_names() -> None:
    reg = AnalyzerRegistry()
    reg.register(_ZahirNoopAnalyzer)
    assert list(reg) == ["zahir_noop"]


def test_contains_matches_by_name() -> None:
    reg = AnalyzerRegistry()
    reg.register(_ZahirNoopAnalyzer)
    assert "zahir_noop" in reg
    assert "not_registered" not in reg
    assert 42 not in reg  # type: ignore[operator]  # non-string lookup is False


def test_instantiate_all_creates_one_instance_per_class() -> None:
    reg = AnalyzerRegistry()
    reg.register(_ZahirNoopAnalyzer)
    reg.register(_BatinNoopAnalyzer)
    instances = reg.instantiate_all()
    assert len(instances) == 2
    assert isinstance(instances[0], _ZahirNoopAnalyzer)
    assert isinstance(instances[1], _BatinNoopAnalyzer)


# ---------------------------------------------------------------------------
# scan_all — execution surface
# ---------------------------------------------------------------------------

def test_scan_all_on_missing_file() -> None:
    reg = AnalyzerRegistry()
    reg.register(_ZahirNoopAnalyzer)
    report = reg.scan_all(Path("/nonexistent/path/to/doc.pdf"))
    assert report.integrity_score == 0.0
    assert report.scan_incomplete is True
    assert report.error is not None
    assert "File not found" in report.error
    assert report.findings == []


def test_scan_all_empty_registry_returns_clean_report(pdf_path: Path) -> None:
    reg = AnalyzerRegistry()
    report = reg.scan_all(pdf_path)
    assert report.integrity_score == 1.0
    assert report.scan_incomplete is False
    assert report.findings == []
    assert report.error is None


def test_scan_all_no_findings_returns_perfect_score(pdf_path: Path) -> None:
    reg = AnalyzerRegistry()
    reg.register(_ZahirNoopAnalyzer)
    reg.register(_BatinNoopAnalyzer)
    report = reg.scan_all(pdf_path)
    assert report.integrity_score == 1.0
    assert report.scan_incomplete is False
    assert report.findings == []


def test_scan_all_concatenates_findings_in_registration_order(pdf_path: Path) -> None:
    reg = AnalyzerRegistry()
    reg.register(_ZwspFireAnalyzer)  # registered first
    reg.register(_JsFireAnalyzer)    # registered second
    report = reg.scan_all(pdf_path)
    assert [f.mechanism for f in report.findings] == [
        "zero_width_chars", "javascript",
    ]


def test_scan_all_recomputes_score_from_merged_findings(pdf_path: Path) -> None:
    reg = AnalyzerRegistry()
    reg.register(_ZwspFireAnalyzer)  # zero_width_chars severity 0.10
    reg.register(_JsFireAnalyzer)    # javascript severity 0.30
    report = reg.scan_all(pdf_path)
    # Expected: 1.0 - 0.10 - 0.30 = 0.60
    assert report.integrity_score == pytest.approx(0.60)


def test_scan_all_score_matches_compute_muwazana_over_merged(pdf_path: Path) -> None:
    """Parity with the domain value object — the registry does NOT
    invent its own scoring."""
    reg = AnalyzerRegistry()
    reg.register(_ZwspFireAnalyzer)
    reg.register(_JsFireAnalyzer)
    report = reg.scan_all(pdf_path)
    expected = compute_muwazana_score(report.findings)
    assert report.integrity_score == expected


def test_scan_all_catches_unexpected_analyzer_exception(pdf_path: Path) -> None:
    reg = AnalyzerRegistry()
    reg.register(_RaisingAnalyzer)
    report = reg.scan_all(pdf_path)
    assert report.error == "Raiser error: analyzer exploded"
    assert report.scan_incomplete is True
    assert report.findings == []


def test_scan_all_one_raiser_does_not_silence_other_analyzers(
    pdf_path: Path,
) -> None:
    """Middle-community invariant — one witness failing does not silence
    the others."""
    reg = AnalyzerRegistry()
    reg.register(_RaisingAnalyzer)
    reg.register(_ZwspFireAnalyzer)
    report = reg.scan_all(pdf_path)
    assert [f.mechanism for f in report.findings] == ["zero_width_chars"]
    assert report.error is not None
    assert "Raiser error: analyzer exploded" in report.error
    assert report.scan_incomplete is True


def test_scan_all_multiple_errors_joined_with_semicolon(pdf_path: Path) -> None:
    """v0.1-compatible 'A; B' format across multiple analyzer errors."""
    reg = AnalyzerRegistry()
    reg.register(_RaisingAnalyzer)
    reg.register(_ExpectedErrorAnalyzer)
    report = reg.scan_all(pdf_path)
    assert report.error is not None
    assert "Raiser error: analyzer exploded" in report.error
    assert "Expected error: couldn't open font stream" in report.error
    # Both errors joined with '; '
    assert "; " in report.error


def test_scan_all_expected_error_emits_scan_error_finding(pdf_path: Path) -> None:
    """Expected-failure path: analyzer returns scan_error via helper."""
    reg = AnalyzerRegistry()
    reg.register(_ExpectedErrorAnalyzer)
    report = reg.scan_all(pdf_path)
    assert len(report.findings) == 1
    assert report.findings[0].mechanism == "scan_error"
    assert report.findings[0].source_layer == "zahir"
    assert report.scan_incomplete is True


def test_scan_all_applies_incomplete_clamp(pdf_path: Path) -> None:
    """Scan-incomplete clamp — merged score is forced down to 0.5 when
    any analyzer is incomplete, even if the findings alone would score
    higher."""
    reg = AnalyzerRegistry()
    reg.register(_ExpectedErrorAnalyzer)     # scan_incomplete=True, no real findings
    reg.register(_ZahirNoopAnalyzer)         # clean
    report = reg.scan_all(pdf_path)
    # Without the clamp, score would be 1.0 (scan_error has severity 0.0).
    # With the clamp, scan_incomplete=True and score <= 0.5.
    assert report.scan_incomplete is True
    assert report.integrity_score == SCAN_INCOMPLETE_CLAMP


def test_scan_all_clamp_not_applied_for_clean_run(pdf_path: Path) -> None:
    reg = AnalyzerRegistry()
    reg.register(_ZwspFireAnalyzer)
    report = reg.scan_all(pdf_path)
    assert report.scan_incomplete is False
    # 1.0 - 0.10 = 0.90, not clamped.
    assert report.integrity_score == pytest.approx(0.90)


def test_scan_all_return_type_and_to_dict_shape(pdf_path: Path) -> None:
    reg = AnalyzerRegistry()
    reg.register(_ZwspFireAnalyzer)
    report = reg.scan_all(pdf_path)
    assert isinstance(report, IntegrityReport)
    d = report.to_dict()
    # Byte-identical parity invariant — verdict_disclaimer is the v0.1
    # verbatim string, and source_layer never leaks into to_dict.
    assert d["verdict_disclaimer"] == VERDICT_DISCLAIMER
    for f in d["findings"]:
        assert "source_layer" not in f


# ---------------------------------------------------------------------------
# Independence — separate registries do not share state
# ---------------------------------------------------------------------------

def test_registries_are_independent() -> None:
    r1 = AnalyzerRegistry()
    r2 = AnalyzerRegistry()
    r1.register(_ZahirNoopAnalyzer)
    assert "zahir_noop" in r1
    assert "zahir_noop" not in r2
