"""
Tests for analyzers.pdf_trailer_analyzer (v1.1.2 Day 2 mechanism 05).

Tier 2 mechanism: non-whitespace bytes after the final %%EOF marker
in a PDF file. Closes pdf_gauntlet fixture 05_after_eof.pdf, which
appends an 85-byte HIDDEN_TEXT_PAYLOAD comment block after the final
%%EOF.

Test pairing per Differentiator Layer 7 GAN paired-fixtures, plus a
mandatory third test (per Day 2 prompt section 6.4) for the
incremental-update false-positive guard:

  - test_catches_fixture_05: adversarial fixture must produce a
    Tier 2 finding with mechanism = "pdf_trailer_analyzer".
  - test_clean_on_control: tests/fixtures/clean.pdf has only a
    single trailing newline after %%EOF (whitespace-only); the
    detector must not fire.
  - test_clean_on_incremental_update_pdf: incremental-update PDFs
    contain MULTIPLE %%EOF markers in series. The detector keys on
    the FINAL %%EOF only and must not fire on a legitimate
    incremental-update file with a clean tail. This is the
    Defense Case F4 falsifiability guard - false positives on
    incremental-update PDFs would void the at-most-5% false-
    positive-rate claim on customer-authored documents.

References:
  - docs/adversarial/pdf_gauntlet/REPORT.md row 05
  - docs/scope/v1_1_2_claude_prompt.md section 6.4
"""
from __future__ import annotations

from pathlib import Path

from analyzers.pdf_trailer_analyzer import detect_pdf_trailer_analyzer
from domain.config import BATIN_MECHANISMS, SEVERITY, TIER, ZAHIR_MECHANISMS


REPO_ROOT = Path(__file__).resolve().parents[2]
ADVERSARIAL_FIXTURE = (
    REPO_ROOT / "docs/adversarial/pdf_gauntlet/fixtures/05_after_eof.pdf"
)
CONTROL_FIXTURE = REPO_ROOT / "tests/fixtures/clean.pdf"
INCREMENTAL_UPDATE_FIXTURE = (
    REPO_ROOT / "tests/fixtures/object/incremental_update.pdf"
)


def test_pdf_trailer_analyzer_registered_in_batin_mechanisms() -> None:
    """The mechanism must appear in BATIN_MECHANISMS (the trailing
    region after %%EOF lives outside both the rendered surface and
    the parsed object graph) with TIER 2 and SEVERITY 0.5 per Day 2
    prompt section 6.6 step 2."""
    assert "pdf_trailer_analyzer" in BATIN_MECHANISMS
    assert "pdf_trailer_analyzer" not in ZAHIR_MECHANISMS
    assert TIER["pdf_trailer_analyzer"] == 2
    assert SEVERITY["pdf_trailer_analyzer"] == 0.5


def test_pdf_trailer_analyzer_catches_fixture_05() -> None:
    """The 85 non-whitespace bytes appended after %%EOF in fixture
    05 must produce exactly one Tier 2 finding."""
    assert ADVERSARIAL_FIXTURE.exists(), (
        f"PDF gauntlet fixture missing: {ADVERSARIAL_FIXTURE}"
    )
    findings = detect_pdf_trailer_analyzer(ADVERSARIAL_FIXTURE)
    matching = [
        f for f in findings
        if f.mechanism == "pdf_trailer_analyzer" and f.tier == 2
    ]
    assert len(matching) >= 1, (
        f"pdf_trailer_analyzer did not fire on fixture 05; got "
        f"{[f.mechanism for f in findings]}"
    )


def test_pdf_trailer_analyzer_clean_on_control() -> None:
    """The v1.0 baseline clean PDF (tests/fixtures/clean.pdf) ends
    with a single newline after %%EOF (whitespace only); the
    detector must return zero findings."""
    assert CONTROL_FIXTURE.exists(), (
        f"Control fixture missing: {CONTROL_FIXTURE}"
    )
    findings = detect_pdf_trailer_analyzer(CONTROL_FIXTURE)
    assert findings == [], (
        f"pdf_trailer_analyzer fired on the clean baseline PDF; got "
        f"{[(f.mechanism, f.location) for f in findings]}"
    )


def test_pdf_trailer_analyzer_clean_on_incremental_update_pdf() -> None:
    """An incremental-update PDF carries multiple %%EOF markers in
    series. The detector must key on the FINAL %%EOF and stay silent
    when the file's tail after the last marker is clean (single
    newline). This is the Defense Case F4 false-positive guard:
    incremental-update PDFs are common in real-world authoring
    workflows (Acrobat saves edits as incremental updates), and
    firing on every such file would void the v1.1.2 false-positive-
    rate budget."""
    assert INCREMENTAL_UPDATE_FIXTURE.exists(), (
        f"Incremental-update fixture missing: {INCREMENTAL_UPDATE_FIXTURE}"
    )
    findings = detect_pdf_trailer_analyzer(INCREMENTAL_UPDATE_FIXTURE)
    assert findings == [], (
        f"pdf_trailer_analyzer false-positived on a legitimate "
        f"incremental-update PDF; got "
        f"{[(f.mechanism, f.location) for f in findings]}"
    )
