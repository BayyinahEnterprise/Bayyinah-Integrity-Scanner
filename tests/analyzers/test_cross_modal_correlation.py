"""
Tests for analyzers.cross_modal_correlation.CrossModalCorrelationEngine.

Phase 25+ — cross-modal correlation post-processor (Al-Baqarah 2:164).
The engine reads the stems the Phase 23/24 analyzers already
separated and emits findings for divergence the individual analyzers
cannot see. It is stateless, idempotent, does not reparse files, and
does not mutate its input report.

Session 1 rule set under test:

  * ``cross_stem_inventory``       — always emitted (non-deducting).
  * ``cross_stem_undeclared_text`` — fires when subtitle / audio-lyric
    stem carries substantive findings AND the metadata stem is
    silent (or its findings do not declare textual content).

These tests pin:

  * API contract — ``correlate`` takes an IntegrityReport, returns a
    list of Finding, does not mutate its input.
  * Idempotence — running the engine twice returns identical outputs.
  * Inventory always fires.
  * The undeclared-text rule fires on the divergent fixture
    (``correlation_undeclared.mp4``).
  * The undeclared-text rule stays silent on the aligned fixture
    (``correlation_aligned.mp4``) — metadata declares captions.
  * The engine is harmless on non-audio/video reports (PDF, DOCX)
    — inventory fires with empty stem counts, no other rules trigger.
  * Mechanisms the engine emits are registered in config.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from analyzers import (
    AudioAnalyzer,
    CrossModalCorrelationEngine,
    VideoAnalyzer,
)
from analyzers.base import BaseAnalyzer
from application import ScanService
from domain import Finding, IntegrityReport
from domain.config import (
    BATIN_MECHANISMS,
    SEVERITY,
    TIER,
    ZAHIR_MECHANISMS,
)


FIXTURES_DIR: Path = (
    Path(__file__).resolve().parent.parent / "fixtures" / "video"
)


@pytest.fixture(scope="module", autouse=True)
def _ensure_video_fixtures_built() -> None:
    from tests.make_video_fixtures import (
        VIDEO_FIXTURE_EXPECTATIONS,
        generate_all,
    )
    missing = [
        FIXTURES_DIR / rel
        for rel in VIDEO_FIXTURE_EXPECTATIONS
        if not (FIXTURES_DIR / rel).exists()
    ]
    if missing:
        generate_all(FIXTURES_DIR)


# ---------------------------------------------------------------------------
# API contract
# ---------------------------------------------------------------------------


def test_engine_is_not_a_base_analyzer_subclass() -> None:
    # The engine is a post-processor, not a per-file analyzer. It
    # MUST NOT inherit from BaseAnalyzer — that would invite the
    # AnalyzerRegistry to treat it as a per-FileKind analyzer and
    # the engine would misfire on every scan.
    assert not issubclass(CrossModalCorrelationEngine, BaseAnalyzer)


def test_engine_instantiable_without_args() -> None:
    engine = CrossModalCorrelationEngine()
    assert engine is not None


def test_correlate_returns_list_of_findings() -> None:
    engine = CrossModalCorrelationEngine()
    report = VideoAnalyzer().scan(FIXTURES_DIR / "clean" / "clean.mp4")
    out = engine.correlate(report)
    assert isinstance(out, list)
    for f in out:
        assert isinstance(f, Finding)


def test_correlate_does_not_mutate_input_report() -> None:
    """The engine is a read-only consumer of the report. Mutating the
    input would silently break callers who keep a reference to the
    original report and expect it unchanged."""
    report = VideoAnalyzer().scan(
        FIXTURES_DIR / "adversarial" / "correlation_undeclared.mp4"
    )
    findings_before = list(report.findings)
    score_before = report.integrity_score
    incomplete_before = report.scan_incomplete

    _ = CrossModalCorrelationEngine().correlate(report)

    assert report.findings == findings_before
    assert report.integrity_score == score_before
    assert report.scan_incomplete == incomplete_before


def test_correlate_is_idempotent() -> None:
    """Running the engine twice on the same report returns identical
    findings. A post-processor that depends on hidden state will fail
    this; a pure one won't."""
    report = VideoAnalyzer().scan(
        FIXTURES_DIR / "adversarial" / "correlation_undeclared.mp4"
    )
    out1 = CrossModalCorrelationEngine().correlate(report)
    out2 = CrossModalCorrelationEngine().correlate(report)
    assert len(out1) == len(out2)
    for a, b in zip(out1, out2):
        assert a.mechanism == b.mechanism
        assert a.severity_override == b.severity_override
        assert a.confidence == b.confidence
        assert a.description == b.description


# ---------------------------------------------------------------------------
# Inventory always fires
# ---------------------------------------------------------------------------


def test_inventory_fires_on_clean_video_fixture() -> None:
    report = VideoAnalyzer().scan(FIXTURES_DIR / "clean" / "clean.mp4")
    out = CrossModalCorrelationEngine().correlate(report)
    mechs = {f.mechanism for f in out}
    assert "cross_stem_inventory" in mechs


def test_inventory_fires_on_adversarial_video_fixture() -> None:
    report = VideoAnalyzer().scan(
        FIXTURES_DIR / "adversarial" / "subtitle_invisible_chars.mp4"
    )
    out = CrossModalCorrelationEngine().correlate(report)
    mechs = {f.mechanism for f in out}
    assert "cross_stem_inventory" in mechs


def test_inventory_is_non_deducting() -> None:
    report = VideoAnalyzer().scan(FIXTURES_DIR / "clean" / "clean.mp4")
    out = CrossModalCorrelationEngine().correlate(report)
    inv = next(f for f in out if f.mechanism == "cross_stem_inventory")
    assert inv.severity_override == 0.0
    assert SEVERITY["cross_stem_inventory"] == 0.0


def test_inventory_fires_even_on_non_audio_video_reports(tmp_path: Path) -> None:
    """A report from an analyzer that doesn't participate in cross-
    modal stems (e.g. PDF / DOCX) should still produce an inventory
    finding — empty stems, but the engine runs without error."""
    # Synthesise an empty IntegrityReport as if a non-media analyzer
    # produced it.
    empty_report = IntegrityReport(
        file_path="dummy.pdf",
        integrity_score=1.0,
        findings=[],
        scan_incomplete=False,
    )
    out = CrossModalCorrelationEngine().correlate(empty_report)
    mechs = {f.mechanism for f in out}
    assert mechs == {"cross_stem_inventory"}


# ---------------------------------------------------------------------------
# cross_stem_undeclared_text — aligned vs divergent paired fixtures
# ---------------------------------------------------------------------------


def test_undeclared_text_fires_on_divergent_fixture() -> None:
    """The divergent fixture: subtitle stem non-silent, metadata stem
    silent. The rule must fire."""
    report = VideoAnalyzer().scan(
        FIXTURES_DIR / "adversarial" / "correlation_undeclared.mp4"
    )
    out = CrossModalCorrelationEngine().correlate(report)
    mechs = {f.mechanism for f in out}
    assert "cross_stem_undeclared_text" in mechs, (
        f"Expected cross_stem_undeclared_text to fire on divergent "
        f"fixture. Got: {mechs}"
    )


def test_undeclared_text_stays_silent_on_aligned_fixture() -> None:
    """The aligned fixture: subtitle stem non-silent, metadata stem
    also non-silent AND declares a caption keyword. The rule must
    stay silent — stems agree on the presence of textual content."""
    report = VideoAnalyzer().scan(
        FIXTURES_DIR / "adversarial" / "correlation_aligned.mp4"
    )
    out = CrossModalCorrelationEngine().correlate(report)
    mechs = {f.mechanism for f in out}
    assert "cross_stem_undeclared_text" not in mechs, (
        f"cross_stem_undeclared_text fired on aligned fixture "
        f"(false positive). Got: {mechs}"
    )


def test_undeclared_text_silent_when_no_subtitle_findings() -> None:
    """A video with no subtitle concealment findings cannot be
    described as 'undeclared text'; the rule must stay silent even
    if the metadata stem is also silent."""
    report = VideoAnalyzer().scan(FIXTURES_DIR / "clean" / "clean.mp4")
    out = CrossModalCorrelationEngine().correlate(report)
    mechs = {f.mechanism for f in out}
    assert "cross_stem_undeclared_text" not in mechs


def test_undeclared_text_silent_when_only_metadata_fires() -> None:
    """A video whose only adversarial finding is in the metadata stem
    (no subtitle content) is not an undeclared-text case — there is
    no subtitle text to be undeclared."""
    report = VideoAnalyzer().scan(
        FIXTURES_DIR / "adversarial" / "metadata_suspicious.mp4"
    )
    out = CrossModalCorrelationEngine().correlate(report)
    mechs = {f.mechanism for f in out}
    assert "cross_stem_undeclared_text" not in mechs


# ---------------------------------------------------------------------------
# Graceful handling of non-media reports
# ---------------------------------------------------------------------------


def test_engine_harmless_on_pdf_report() -> None:
    """A PDF scan produces findings the engine does not understand.
    The engine must run cleanly — inventory with empty stems,
    no other rules fire, no exceptions propagate."""
    pdf = Path("tests/fixtures/clean.pdf")
    if not pdf.exists():
        pytest.skip("PDF fixture not generated")
    report = ScanService().scan(pdf)
    out = CrossModalCorrelationEngine().correlate(report)
    # Inventory fires. No cross_stem_* deducting mechanism fires.
    deducting = [
        f for f in out
        if f.mechanism != "cross_stem_inventory"
    ]
    assert deducting == [], (
        f"Engine fired deducting rules on a PDF report: {deducting}"
    )


# ---------------------------------------------------------------------------
# Mechanism registry coherence
# ---------------------------------------------------------------------------


_CROSS_MECHS: set[str] = {
    "cross_stem_inventory",
    "cross_stem_undeclared_text",
}


def test_every_cross_modal_mechanism_is_registered() -> None:
    combined = ZAHIR_MECHANISMS | BATIN_MECHANISMS
    missing = _CROSS_MECHS - combined
    assert not missing, f"unregistered cross-modal mechanisms: {missing}"


def test_every_cross_modal_mechanism_has_severity_and_tier() -> None:
    for m in _CROSS_MECHS:
        assert m in SEVERITY, f"{m} missing SEVERITY"
        assert m in TIER, f"{m} missing TIER"
        assert 0.0 <= SEVERITY[m] <= 1.0
        assert TIER[m] in (1, 2, 3)


def test_cross_mechanisms_are_batin() -> None:
    # Cross-modal correlation is post-decompose structural analysis.
    # Both mechanisms belong to the batin classification.
    for m in _CROSS_MECHS:
        assert m in BATIN_MECHANISMS, f"{m} should be batin-classified"


def test_undeclared_text_severity_matches_calibration() -> None:
    # Calibrated to match video_metadata_suspicious (the cross-stem
    # analogue) at 0.25.
    assert SEVERITY["cross_stem_undeclared_text"] == 0.25


# ---------------------------------------------------------------------------
# Extensibility — custom rule sets
# ---------------------------------------------------------------------------


def test_engine_accepts_custom_rule_tuple() -> None:
    """Future sessions will extend the rule set. The engine must
    accept an explicit rule tuple so individual rules can be tested
    in isolation and new rules can be swapped in without forking
    the engine."""
    def _always_silent_rule(report, stems):
        return []

    engine = CrossModalCorrelationEngine(rules=(_always_silent_rule,))
    report = VideoAnalyzer().scan(
        FIXTURES_DIR / "adversarial" / "correlation_undeclared.mp4"
    )
    out = engine.correlate(report)
    # With only the no-op rule, the engine produces zero findings —
    # even the inventory does not fire, because inventory is itself
    # a rule in the default tuple.
    assert out == []


def test_engine_uses_default_rules_when_none_passed() -> None:
    """Default rules tuple contains at least the inventory and the
    undeclared-text rule."""
    engine = CrossModalCorrelationEngine()
    # Confidence that at least two rules are wired up — precise count
    # should grow additively in later sessions.
    assert len(engine._rules) >= 2
