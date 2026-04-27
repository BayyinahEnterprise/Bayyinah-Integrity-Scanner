"""
Tests for analyzers.pdf_metadata_analyzer (v1.1.2 Day 2 mechanism 04).

Tier 1 mechanism: structural anomalies in the /Info dictionary and
the XMP metadata stream. Closes pdf_gauntlet fixture 04_metadata.pdf,
which carries the HIDDEN_TEXT_PAYLOAD in /Info /Keywords, /Info
/Subject, and XMP dc:description.

Test pairing per Differentiator Layer 7 GAN paired-fixtures:
  - test_catches_fixture_04: adversarial fixture must produce at
    least one Tier 1 finding with mechanism = "pdf_metadata_analyzer".
    The detector emits per-field findings (one per anomalous field),
    so the assertion checks for >= 1 such finding rather than an
    exact count - the precise count is implementation detail of the
    divergence-eligible field set.
  - test_clean_on_control: tests/fixtures/clean.pdf has legitimate
    /Info entries (Title, Author, Creator, Subject, Producer) but
    no /Keywords, no XMP dc:description, no XMP pdf:Keywords - none
    of the divergence-eligible fields are populated, so the
    detector must return zero findings.

References:
  - docs/adversarial/pdf_gauntlet/REPORT.md row 04
  - docs/scope/v1_1_2_claude_prompt.md section 6.3
"""
from __future__ import annotations

from pathlib import Path

from analyzers.pdf_metadata_analyzer import detect_pdf_metadata_analyzer
from domain.config import BATIN_MECHANISMS, SEVERITY, TIER, ZAHIR_MECHANISMS


REPO_ROOT = Path(__file__).resolve().parents[2]
ADVERSARIAL_FIXTURE = (
    REPO_ROOT / "docs/adversarial/pdf_gauntlet/fixtures/04_metadata.pdf"
)
CONTROL_FIXTURE = REPO_ROOT / "tests/fixtures/clean.pdf"


def test_pdf_metadata_analyzer_registered_in_batin_mechanisms() -> None:
    """The mechanism must appear in BATIN_MECHANISMS (the /Info dict
    and XMP stream live in the PDF object graph, not the rendered
    surface) with TIER 1 and SEVERITY 1.0 per Day 2 prompt section
    6.6 step 2."""
    assert "pdf_metadata_analyzer" in BATIN_MECHANISMS
    assert "pdf_metadata_analyzer" not in ZAHIR_MECHANISMS
    assert TIER["pdf_metadata_analyzer"] == 1
    assert SEVERITY["pdf_metadata_analyzer"] == 1.0


def test_pdf_metadata_analyzer_catches_fixture_04() -> None:
    """The HIDDEN_TEXT_PAYLOAD in /Info /Keywords and XMP
    dc:description (both divergence-eligible content-summary fields)
    must produce at least one Tier 1 finding."""
    assert ADVERSARIAL_FIXTURE.exists(), (
        f"PDF gauntlet fixture missing: {ADVERSARIAL_FIXTURE}"
    )
    findings = detect_pdf_metadata_analyzer(ADVERSARIAL_FIXTURE)
    matching = [
        f for f in findings
        if f.mechanism == "pdf_metadata_analyzer" and f.tier == 1
    ]
    assert len(matching) >= 1, (
        f"pdf_metadata_analyzer did not fire on fixture 04; got "
        f"{[f.mechanism for f in findings]}"
    )


def test_pdf_metadata_analyzer_clean_on_control() -> None:
    """The v1.0 baseline clean PDF (tests/fixtures/clean.pdf) has
    legitimate /Info entries but none of the divergence-eligible
    content-summary fields populated; the detector must return zero
    findings."""
    assert CONTROL_FIXTURE.exists(), (
        f"Control fixture missing: {CONTROL_FIXTURE}"
    )
    findings = detect_pdf_metadata_analyzer(CONTROL_FIXTURE)
    assert all(f.mechanism != "pdf_metadata_analyzer" for f in findings), (
        f"pdf_metadata_analyzer fired on the clean baseline PDF; got "
        f"{[(f.mechanism, f.location) for f in findings]}"
    )
