"""
v1.7.0 (Round 17) Q5 cross-modal correlation policy contract pin.

Pins docs/cross_modal.md properties P1 through P4. Modifications that
break any of these tests are regressions requiring the parity-break
ceremony per PARITY.md.

Per CODING_STRATEGY §6 v1.7.0: this release documents the existing
substrate-actual policy (Phase 12 default-on, Phase 25+ opt-in) and
pins it via the tests below. The release does NOT modify
ScanService.scan() behavior. STANDARD audit-intensity.

Verse 2:148 anchor: the scanner faces one direction (default cross-
layer correlation via Phase 12); a second direction (stem-level
correlation via Phase 25+) is reserved opt-in until the rule set
stabilizes.
"""
from __future__ import annotations

from application.scan_service import ScanService
from analyzers import CorrelationEngine, CrossModalCorrelationEngine
from analyzers.base import BaseAnalyzer
from domain.config import MECHANISM_REGISTRY


# ---------------------------------------------------------------------------
# P1. Phase 12 CorrelationEngine default-on invariant
# ---------------------------------------------------------------------------


class TestPhase12DefaultOn:
    """ScanService default-constructed instance carries a CorrelationEngine."""

    def test_default_scan_service_has_correlation_engine(self) -> None:
        """A ScanService() with no args has a CorrelationEngine attached."""
        svc = ScanService()
        assert hasattr(svc, "correlation_engine")
        assert svc.correlation_engine is not None
        assert isinstance(svc.correlation_engine, CorrelationEngine)

    def test_default_correlation_engine_is_phase_12(self) -> None:
        """The default is Phase 12 CorrelationEngine, not Phase 25+."""
        svc = ScanService()
        # Phase 12 engine; NOT Phase 25+ CrossModalCorrelationEngine
        assert isinstance(svc.correlation_engine, CorrelationEngine)
        assert not isinstance(svc.correlation_engine, CrossModalCorrelationEngine)

    def test_correlation_engine_exposes_intra_file_correlate(self) -> None:
        """Phase 12 engine provides intra_file_correlate."""
        engine = CorrelationEngine()
        assert hasattr(engine, "intra_file_correlate")
        assert callable(engine.intra_file_correlate)

    def test_correlation_engine_exposes_cross_file_correlate(self) -> None:
        """Phase 12 engine provides cross_file_correlate."""
        engine = CorrelationEngine()
        assert hasattr(engine, "cross_file_correlate")
        assert callable(engine.cross_file_correlate)


# ---------------------------------------------------------------------------
# P2. Phase 25+ CrossModalCorrelationEngine default-off invariant
# ---------------------------------------------------------------------------


class TestPhase25PlusDefaultOff:
    """ScanService does NOT invoke Phase 25+ engine as a side effect."""

    def test_default_scan_service_correlation_engine_is_not_phase_25(self) -> None:
        """The default correlation_engine slot is NOT a Phase 25+ engine."""
        svc = ScanService()
        assert not isinstance(svc.correlation_engine, CrossModalCorrelationEngine)

    def test_phase_25_engine_is_not_a_base_analyzer(self) -> None:
        """Phase 25+ engine is a post-processor, NOT a BaseAnalyzer subclass.

        BaseAnalyzer subclasses are automatically dispatched by the
        AnalyzerRegistry. If Phase 25+ were a BaseAnalyzer it would be
        invoked on every scan; it must NOT be.
        """
        assert not issubclass(CrossModalCorrelationEngine, BaseAnalyzer)

    def test_phase_25_engine_has_explicit_correlate_method(self) -> None:
        """Phase 25+ opt-in invocation is via CrossModalCorrelationEngine().correlate()."""
        engine = CrossModalCorrelationEngine()
        assert hasattr(engine, "correlate")
        assert callable(engine.correlate)


# ---------------------------------------------------------------------------
# P3. Public surface invariant
# ---------------------------------------------------------------------------


class TestPublicSurface:
    """Both engines must remain importable from the analyzers package."""

    def test_correlation_engine_importable(self) -> None:
        """analyzers.CorrelationEngine is the Phase 12 public name."""
        from analyzers import CorrelationEngine as imported
        assert imported is CorrelationEngine

    def test_cross_modal_correlation_engine_importable(self) -> None:
        """analyzers.CrossModalCorrelationEngine is the Phase 25+ public name."""
        from analyzers import CrossModalCorrelationEngine as imported
        assert imported is CrossModalCorrelationEngine

    def test_two_distinct_engines(self) -> None:
        """The two engines are distinct classes; one does not subclass the other."""
        assert CorrelationEngine is not CrossModalCorrelationEngine
        assert not issubclass(CorrelationEngine, CrossModalCorrelationEngine)
        assert not issubclass(CrossModalCorrelationEngine, CorrelationEngine)


# ---------------------------------------------------------------------------
# P4. Mechanism-registry stability
# ---------------------------------------------------------------------------


class TestMechanismRegistryStability:
    """Cross-modal mechanism names in MECHANISM_REGISTRY are pinned at v1.7.0."""

    def test_cross_format_payload_match_present(self) -> None:
        """Phase 12 cross-file correlation mechanism is in the registry."""
        assert "cross_format_payload_match" in MECHANISM_REGISTRY

    def test_cross_stem_inventory_present(self) -> None:
        """Phase 25+ inventory mechanism is in the registry."""
        assert "cross_stem_inventory" in MECHANISM_REGISTRY

    def test_cross_stem_undeclared_text_present(self) -> None:
        """Phase 25+ undeclared-text mechanism is in the registry."""
        assert "cross_stem_undeclared_text" in MECHANISM_REGISTRY

    def test_audio_cross_stem_divergence_present(self) -> None:
        """Audio cross-stem divergence mechanism is in the registry."""
        assert "audio_cross_stem_divergence" in MECHANISM_REGISTRY

    def test_video_cross_stem_divergence_present(self) -> None:
        """Video cross-stem divergence mechanism is in the registry."""
        assert "video_cross_stem_divergence" in MECHANISM_REGISTRY

    def test_no_new_cross_modal_mechanisms_at_v170(self) -> None:
        """At v1.7.0 the cross-modal-related mechanism set is exactly 5.

        Future releases that wire additional Phase 25+ rules must extend
        MECHANISM_REGISTRY and either update this test or invoke the
        parity-break ceremony.
        """
        cross_modal_mechs = {
            m for m in MECHANISM_REGISTRY
            if "cross_stem" in m or "cross_format_payload_match" == m
            or "cross_modal" in m
        }
        assert cross_modal_mechs == {
            "audio_cross_stem_divergence",
            "cross_format_payload_match",
            "cross_stem_inventory",
            "cross_stem_undeclared_text",
            "video_cross_stem_divergence",
        }


# ---------------------------------------------------------------------------
# Composition invariant: opt-in path works as documented
# ---------------------------------------------------------------------------


class TestOptInComposition:
    """The opt-in invocation pattern documented in docs/cross_modal.md works."""

    def test_phase_25_engine_correlates_a_minimal_report(self) -> None:
        """Constructing the engine and calling correlate() on an empty report
        does not raise. Specific findings shapes are tested in
        tests/analyzers/test_cross_modal_correlation.py; this contract test
        pins only that the opt-in invocation surface remains callable."""
        from domain import IntegrityReport
        engine = CrossModalCorrelationEngine()
        empty_report = IntegrityReport(
            file_path="contract-test",
            integrity_score=1.0,
            findings=[],
            error=None,
            scan_incomplete=False,
        )
        out = engine.correlate(empty_report)
        # Empty input may return any of: empty list, list with inventory finding,
        # or implementation-defined inventory placeholder. Contract only pins
        # that the method returns a list-like object and does not raise.
        assert hasattr(out, "__iter__")
