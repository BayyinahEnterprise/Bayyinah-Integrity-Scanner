"""
Tests for analyzers.pdf_off_page_text (v1.1.2 Day 2 mechanism 03).

Tier 1 mechanism: text-matrix Tm origin outside the page MediaBox.
Closes pdf_gauntlet fixture 03_off_page.pdf, which the v1.1.1
ZahirTextAnalyzer._check_offpage path missed because PyMuPDF's
get_text('dict') silently drops spans whose origin is below the
page rectangle. The new detector reads the raw content stream via
pikepdf, bypassing that drop.

Test pairing per Differentiator Layer 7 GAN paired-fixtures:
  - test_catches_fixture_03: adversarial fixture must produce a
    Tier 1 finding with mechanism = "pdf_off_page_text".
  - test_clean_on_control: the v1.0 baseline clean PDF
    (tests/fixtures/clean.pdf) must produce zero pdf_off_page_text
    findings. The fixture is the long-standing v1.0 control PDF
    that the existing PDF analyzer suite uses for its no-false-
    positive checks.

References:
  - docs/adversarial/pdf_gauntlet/REPORT.md row 03
  - docs/scope/v1_1_2_claude_prompt.md section 6.2
"""
from __future__ import annotations

from pathlib import Path

from analyzers.pdf_off_page_text import detect_pdf_off_page_text
from domain.config import BATIN_MECHANISMS, SEVERITY, TIER, ZAHIR_MECHANISMS


REPO_ROOT = Path(__file__).resolve().parents[2]
ADVERSARIAL_FIXTURE = (
    REPO_ROOT / "docs/adversarial/pdf_gauntlet/fixtures/03_off_page.pdf"
)
CONTROL_FIXTURE = REPO_ROOT / "tests/fixtures/clean.pdf"


def test_pdf_off_page_text_registered_in_zahir_mechanisms() -> None:
    """The mechanism classifies as zahir (it parallels the existing
    zahir off_page_text; the Tm origin coordinate is observable from
    the content stream's text-rendering operators with no hidden-
    state inference). TIER is 1 and SEVERITY is 1.0 per Day 2
    prompt section 6.6 step 2."""
    assert "pdf_off_page_text" in ZAHIR_MECHANISMS
    assert "pdf_off_page_text" not in BATIN_MECHANISMS
    assert TIER["pdf_off_page_text"] == 1
    assert SEVERITY["pdf_off_page_text"] == 1.0


def test_pdf_off_page_text_catches_fixture_03() -> None:
    """The off-page Tm at (72, -200) in fixture 03 must produce a
    Tier 1 finding."""
    assert ADVERSARIAL_FIXTURE.exists(), (
        f"PDF gauntlet fixture missing: {ADVERSARIAL_FIXTURE}"
    )
    findings = detect_pdf_off_page_text(ADVERSARIAL_FIXTURE)
    matching = [
        f for f in findings
        if f.mechanism == "pdf_off_page_text" and f.tier == 1
    ]
    assert len(matching) >= 1, (
        f"pdf_off_page_text did not fire on fixture 03; got "
        f"{[f.mechanism for f in findings]}"
    )


def test_pdf_off_page_text_clean_on_control() -> None:
    """The v1.0 baseline clean PDF (tests/fixtures/clean.pdf) has
    only on-page text and must NOT produce a pdf_off_page_text
    finding."""
    assert CONTROL_FIXTURE.exists(), (
        f"Control fixture missing: {CONTROL_FIXTURE}"
    )
    findings = detect_pdf_off_page_text(CONTROL_FIXTURE)
    assert all(f.mechanism != "pdf_off_page_text" for f in findings), (
        f"pdf_off_page_text fired on the clean baseline PDF; got "
        f"{[f.mechanism for f in findings]}"
    )
