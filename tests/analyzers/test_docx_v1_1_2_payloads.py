"""
Tests for the six v1.1.2 DOCX hidden-text payload detectors.

Each mechanism gets the standard paired-fixture trio per
Differentiator Layer 7:

  - REGISTRY: classified into the right source layer with the
    expected TIER and SEVERITY.
  - CATCH: the matching docx_gauntlet fixture produces at least
    one finding from that mechanism.
  - PAYLOAD RECOVERY: the catching finding's ``concealed`` field
    contains the hidden payload bytes (``HIDDEN_TEXT_PAYLOAD`` or
    ``$10,000``), so a reviewer reading the report can read what
    was hidden.
  - CLEAN: the v1.0 baseline clean DOCX (tests/fixtures/docx/
    clean/clean.docx) produces zero findings from that mechanism.

Mechanism table (matches docs/adversarial/docx_gauntlet/REPORT.md):

  | Mechanism                       | Tier | Layer | Sev | Fixture |
  |---------------------------------|------|-------|-----|---------|
  | docx_white_text                 | 1    | zahir | 1.00| 01      |
  | docx_microscopic_font           | 2    | zahir | 0.50| 02      |
  | docx_metadata_payload           | 1    | batin | 1.00| 03      |
  | docx_comment_payload            | 2    | batin | 0.50| 04      |
  | docx_header_footer_payload      | 1    | zahir | 1.00| 05      |
  | docx_orphan_footnote            | 1    | batin | 1.00| 06      |
"""
from __future__ import annotations

from pathlib import Path

import pytest

from analyzers.docx_white_text import detect_docx_white_text
from analyzers.docx_microscopic_font import detect_docx_microscopic_font
from analyzers.docx_metadata_payload import detect_docx_metadata_payload
from analyzers.docx_comment_payload import detect_docx_comment_payload
from analyzers.docx_header_footer_payload import (
    detect_docx_header_footer_payload,
)
from analyzers.docx_orphan_footnote import detect_docx_orphan_footnote
from domain.config import BATIN_MECHANISMS, SEVERITY, TIER, ZAHIR_MECHANISMS


REPO_ROOT = Path(__file__).resolve().parents[2]
GAUNTLET_DIR = REPO_ROOT / "docs/adversarial/docx_gauntlet/fixtures"
CONTROL_FIXTURE = REPO_ROOT / "tests/fixtures/docx/clean/clean.docx"

PAYLOAD_MARKERS = ("HIDDEN_TEXT_PAYLOAD", "$10,000", "10,000")


def _payload_recovered(concealed: str) -> bool:
    """Return True when the concealed string contains any canonical
    payload marker. Mirrors the gauntlet runner's primary-path
    recovery check.
    """
    return any(marker in concealed for marker in PAYLOAD_MARKERS)


# ---------------------------------------------------------------------------
# Registry checks
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "mechanism,layer,tier_value,severity_value",
    [
        ("docx_white_text",            "zahir", 1, 1.0),
        ("docx_microscopic_font",      "zahir", 2, 0.5),
        ("docx_header_footer_payload", "zahir", 1, 1.0),
        ("docx_metadata_payload",      "batin", 1, 1.0),
        ("docx_comment_payload",       "batin", 2, 0.5),
        ("docx_orphan_footnote",       "batin", 1, 1.0),
    ],
)
def test_v1_1_2_docx_mechanism_is_registered(
    mechanism: str,
    layer: str,
    tier_value: int,
    severity_value: float,
) -> None:
    """Every v1.1.2 DOCX mechanism is registered in the right layer
    with the right tier and severity. A drift here means SEVERITY,
    TIER, or the layer set was edited without the matching update
    in the others.
    """
    if layer == "zahir":
        assert mechanism in ZAHIR_MECHANISMS
        assert mechanism not in BATIN_MECHANISMS
    else:
        assert mechanism in BATIN_MECHANISMS
        assert mechanism not in ZAHIR_MECHANISMS
    assert TIER[mechanism] == tier_value
    assert SEVERITY[mechanism] == severity_value


# ---------------------------------------------------------------------------
# docx_white_text — fixture 01
# ---------------------------------------------------------------------------


def test_docx_white_text_catches_fixture_01() -> None:
    fixture = GAUNTLET_DIR / "01_white_on_white.docx"
    assert fixture.exists(), f"missing fixture: {fixture}"
    findings = detect_docx_white_text(fixture)
    matching = [
        f for f in findings
        if f.mechanism == "docx_white_text" and f.tier == 1
    ]
    assert len(matching) >= 1, (
        f"docx_white_text did not fire on fixture 01; got "
        f"{[f.mechanism for f in findings]}"
    )


def test_docx_white_text_recovers_payload_into_concealed() -> None:
    fixture = GAUNTLET_DIR / "01_white_on_white.docx"
    findings = detect_docx_white_text(fixture)
    assert any(
        f.mechanism == "docx_white_text" and _payload_recovered(f.concealed)
        for f in findings
    ), (
        "no docx_white_text finding recovered HIDDEN_TEXT_PAYLOAD; "
        f"concealed values: {[f.concealed[:80] for f in findings]}"
    )


def test_docx_white_text_clean_on_control() -> None:
    assert CONTROL_FIXTURE.exists(), f"missing control: {CONTROL_FIXTURE}"
    findings = detect_docx_white_text(CONTROL_FIXTURE)
    assert all(f.mechanism != "docx_white_text" for f in findings), (
        f"docx_white_text fired on clean baseline; got {findings}"
    )


# ---------------------------------------------------------------------------
# docx_microscopic_font — fixture 02
# ---------------------------------------------------------------------------


def test_docx_microscopic_font_catches_fixture_02() -> None:
    fixture = GAUNTLET_DIR / "02_microscopic_font.docx"
    assert fixture.exists(), f"missing fixture: {fixture}"
    findings = detect_docx_microscopic_font(fixture)
    matching = [
        f for f in findings
        if f.mechanism == "docx_microscopic_font" and f.tier == 2
    ]
    assert len(matching) >= 1, (
        f"docx_microscopic_font did not fire on fixture 02; got "
        f"{[f.mechanism for f in findings]}"
    )


def test_docx_microscopic_font_recovers_payload_into_concealed() -> None:
    fixture = GAUNTLET_DIR / "02_microscopic_font.docx"
    findings = detect_docx_microscopic_font(fixture)
    assert any(
        f.mechanism == "docx_microscopic_font"
        and _payload_recovered(f.concealed)
        for f in findings
    ), (
        "no docx_microscopic_font finding recovered the payload; "
        f"concealed values: {[f.concealed[:80] for f in findings]}"
    )


def test_docx_microscopic_font_clean_on_control() -> None:
    findings = detect_docx_microscopic_font(CONTROL_FIXTURE)
    assert all(
        f.mechanism != "docx_microscopic_font" for f in findings
    ), (
        f"docx_microscopic_font fired on clean baseline; got {findings}"
    )


# ---------------------------------------------------------------------------
# docx_metadata_payload — fixture 03
# ---------------------------------------------------------------------------


def test_docx_metadata_payload_catches_fixture_03() -> None:
    fixture = GAUNTLET_DIR / "03_custom_xml_properties.docx"
    assert fixture.exists(), f"missing fixture: {fixture}"
    findings = detect_docx_metadata_payload(fixture)
    matching = [
        f for f in findings
        if f.mechanism == "docx_metadata_payload" and f.tier == 1
    ]
    assert len(matching) >= 1, (
        f"docx_metadata_payload did not fire on fixture 03; got "
        f"{[f.mechanism for f in findings]}"
    )


def test_docx_metadata_payload_recovers_payload_into_concealed() -> None:
    fixture = GAUNTLET_DIR / "03_custom_xml_properties.docx"
    findings = detect_docx_metadata_payload(fixture)
    assert any(
        f.mechanism == "docx_metadata_payload"
        and _payload_recovered(f.concealed)
        for f in findings
    ), (
        "no docx_metadata_payload finding recovered the payload; "
        f"concealed values: {[f.concealed[:80] for f in findings]}"
    )


def test_docx_metadata_payload_clean_on_control() -> None:
    findings = detect_docx_metadata_payload(CONTROL_FIXTURE)
    assert all(
        f.mechanism != "docx_metadata_payload" for f in findings
    ), (
        f"docx_metadata_payload fired on clean baseline; got {findings}"
    )


# ---------------------------------------------------------------------------
# docx_comment_payload — fixture 04
# ---------------------------------------------------------------------------


def test_docx_comment_payload_catches_fixture_04() -> None:
    fixture = GAUNTLET_DIR / "04_comment_payload.docx"
    assert fixture.exists(), f"missing fixture: {fixture}"
    findings = detect_docx_comment_payload(fixture)
    matching = [
        f for f in findings
        if f.mechanism == "docx_comment_payload" and f.tier == 2
    ]
    assert len(matching) >= 1, (
        f"docx_comment_payload did not fire on fixture 04; got "
        f"{[f.mechanism for f in findings]}"
    )


def test_docx_comment_payload_recovers_payload_into_concealed() -> None:
    fixture = GAUNTLET_DIR / "04_comment_payload.docx"
    findings = detect_docx_comment_payload(fixture)
    assert any(
        f.mechanism == "docx_comment_payload"
        and _payload_recovered(f.concealed)
        for f in findings
    ), (
        "no docx_comment_payload finding recovered the payload; "
        f"concealed values: {[f.concealed[:80] for f in findings]}"
    )


def test_docx_comment_payload_clean_on_control() -> None:
    findings = detect_docx_comment_payload(CONTROL_FIXTURE)
    assert all(
        f.mechanism != "docx_comment_payload" for f in findings
    ), (
        f"docx_comment_payload fired on clean baseline; got {findings}"
    )


# ---------------------------------------------------------------------------
# docx_header_footer_payload — fixture 05
# ---------------------------------------------------------------------------


def test_docx_header_footer_payload_catches_fixture_05() -> None:
    fixture = GAUNTLET_DIR / "05_header_payload.docx"
    assert fixture.exists(), f"missing fixture: {fixture}"
    findings = detect_docx_header_footer_payload(fixture)
    matching = [
        f for f in findings
        if f.mechanism == "docx_header_footer_payload" and f.tier == 1
    ]
    assert len(matching) >= 1, (
        f"docx_header_footer_payload did not fire on fixture 05; got "
        f"{[f.mechanism for f in findings]}"
    )


def test_docx_header_footer_payload_recovers_payload_into_concealed() -> None:
    fixture = GAUNTLET_DIR / "05_header_payload.docx"
    findings = detect_docx_header_footer_payload(fixture)
    assert any(
        f.mechanism == "docx_header_footer_payload"
        and _payload_recovered(f.concealed)
        for f in findings
    ), (
        "no docx_header_footer_payload finding recovered the payload; "
        f"concealed values: {[f.concealed[:80] for f in findings]}"
    )


def test_docx_header_footer_payload_clean_on_control() -> None:
    findings = detect_docx_header_footer_payload(CONTROL_FIXTURE)
    assert all(
        f.mechanism != "docx_header_footer_payload" for f in findings
    ), (
        f"docx_header_footer_payload fired on clean baseline; got {findings}"
    )


# ---------------------------------------------------------------------------
# docx_orphan_footnote — fixture 06
# ---------------------------------------------------------------------------


def test_docx_orphan_footnote_catches_fixture_06() -> None:
    fixture = GAUNTLET_DIR / "06_footnote_payload.docx"
    assert fixture.exists(), f"missing fixture: {fixture}"
    findings = detect_docx_orphan_footnote(fixture)
    matching = [
        f for f in findings
        if f.mechanism == "docx_orphan_footnote" and f.tier == 1
    ]
    assert len(matching) >= 1, (
        f"docx_orphan_footnote did not fire on fixture 06; got "
        f"{[f.mechanism for f in findings]}"
    )


def test_docx_orphan_footnote_recovers_payload_into_concealed() -> None:
    fixture = GAUNTLET_DIR / "06_footnote_payload.docx"
    findings = detect_docx_orphan_footnote(fixture)
    assert any(
        f.mechanism == "docx_orphan_footnote"
        and _payload_recovered(f.concealed)
        for f in findings
    ), (
        "no docx_orphan_footnote finding recovered the payload; "
        f"concealed values: {[f.concealed[:80] for f in findings]}"
    )


def test_docx_orphan_footnote_clean_on_control() -> None:
    findings = detect_docx_orphan_footnote(CONTROL_FIXTURE)
    assert all(
        f.mechanism != "docx_orphan_footnote" for f in findings
    ), (
        f"docx_orphan_footnote fired on clean baseline; got {findings}"
    )


# ---------------------------------------------------------------------------
# Cross-mechanism: each gauntlet fixture closes via exactly one
# v1.1.2 DOCX mechanism. Catches over-firing (a detector reaching
# into a fixture that is meant for a different mechanism).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fixture_filename,expected_mechanism",
    [
        ("01_white_on_white.docx",        "docx_white_text"),
        ("02_microscopic_font.docx",      "docx_microscopic_font"),
        ("03_custom_xml_properties.docx", "docx_metadata_payload"),
        ("04_comment_payload.docx",       "docx_comment_payload"),
        ("05_header_payload.docx",        "docx_header_footer_payload"),
        ("06_footnote_payload.docx",      "docx_orphan_footnote"),
    ],
)
def test_each_gauntlet_fixture_closes_via_exactly_one_v1_1_2_mechanism(
    fixture_filename: str,
    expected_mechanism: str,
) -> None:
    """Run all six v1.1.2 detectors against each fixture and confirm
    only the expected mechanism fires. Flags over-firing (a detector
    that reaches into the wrong fixture) and under-firing (a detector
    that misses its own fixture).
    """
    fixture = GAUNTLET_DIR / fixture_filename
    assert fixture.exists(), f"missing fixture: {fixture}"

    detectors = {
        "docx_white_text": detect_docx_white_text,
        "docx_microscopic_font": detect_docx_microscopic_font,
        "docx_metadata_payload": detect_docx_metadata_payload,
        "docx_comment_payload": detect_docx_comment_payload,
        "docx_header_footer_payload": detect_docx_header_footer_payload,
        "docx_orphan_footnote": detect_docx_orphan_footnote,
    }
    fired: list[str] = []
    for name, fn in detectors.items():
        findings = fn(fixture)
        if any(f.mechanism == name for f in findings):
            fired.append(name)
    assert fired == [expected_mechanism], (
        f"fixture {fixture_filename}: expected only "
        f"{expected_mechanism} to fire; instead fired {fired}"
    )
