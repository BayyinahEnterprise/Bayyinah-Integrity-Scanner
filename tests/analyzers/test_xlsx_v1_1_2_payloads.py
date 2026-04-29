"""
Tests for the six v1.1.2 XLSX hidden-text payload detectors.

Each mechanism gets the standard paired-fixture trio per
Differentiator Layer 7:

  - REGISTRY: classified into the right source layer with the
    expected TIER and SEVERITY.
  - CATCH: the matching xlsx_gauntlet fixture produces at least
    one finding from that mechanism.
  - PAYLOAD RECOVERY: the catching finding's ``concealed`` field
    contains the hidden payload bytes (``HIDDEN_TEXT_PAYLOAD`` or
    ``$10,000``), so a reviewer reading the report can read what
    was hidden.
  - CLEAN: the v1.0 baseline clean XLSX (tests/fixtures/xlsx/
    clean/clean.xlsx) produces zero findings from that mechanism.

Mechanism table (matches docs/adversarial/xlsx_gauntlet/REPORT.md):

  | Mechanism                       | Tier | Layer | Sev | Fixture |
  |---------------------------------|------|-------|-----|---------|
  | xlsx_white_text                 | 1    | zahir | 1.00| 01      |
  | xlsx_microscopic_font           | 2    | zahir | 0.50| 02      |
  | xlsx_defined_name_payload       | 2    | batin | 0.50| 03      |
  | xlsx_comment_payload            | 2    | batin | 0.50| 04      |
  | xlsx_metadata_payload           | 1    | batin | 1.00| 05      |
  | xlsx_csv_injection_formula      | 1    | zahir | 1.00| 06      |
"""
from __future__ import annotations

from pathlib import Path

import pytest

from analyzers.xlsx_white_text import detect_xlsx_white_text
from analyzers.xlsx_microscopic_font import detect_xlsx_microscopic_font
from analyzers.xlsx_defined_name_payload import (
    detect_xlsx_defined_name_payload,
)
from analyzers.xlsx_comment_payload import detect_xlsx_comment_payload
from analyzers.xlsx_metadata_payload import detect_xlsx_metadata_payload
from analyzers.xlsx_csv_injection_formula import (
    detect_xlsx_csv_injection_formula,
)
from domain.config import BATIN_MECHANISMS, SEVERITY, TIER, ZAHIR_MECHANISMS


REPO_ROOT = Path(__file__).resolve().parents[2]
GAUNTLET_DIR = REPO_ROOT / "docs/adversarial/xlsx_gauntlet/fixtures"
CONTROL_FIXTURE = REPO_ROOT / "tests/fixtures/xlsx/clean/clean.xlsx"

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
        ("xlsx_white_text",            "zahir", 1, 1.0),
        ("xlsx_microscopic_font",      "zahir", 2, 0.5),
        ("xlsx_csv_injection_formula", "zahir", 1, 1.0),
        ("xlsx_metadata_payload",      "batin", 1, 1.0),
        ("xlsx_defined_name_payload",  "batin", 2, 0.5),
        ("xlsx_comment_payload",       "batin", 2, 0.5),
    ],
)
def test_v1_1_2_xlsx_mechanism_is_registered(
    mechanism: str,
    layer: str,
    tier_value: int,
    severity_value: float,
) -> None:
    """Every v1.1.2 XLSX mechanism is registered in the right layer
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
# xlsx_white_text — fixture 01
# ---------------------------------------------------------------------------


def test_xlsx_white_text_catches_fixture_01() -> None:
    fixture = GAUNTLET_DIR / "01_white_cell_text.xlsx"
    assert fixture.exists(), f"missing fixture: {fixture}"
    findings = detect_xlsx_white_text(fixture)
    matching = [
        f for f in findings
        if f.mechanism == "xlsx_white_text" and f.tier == 1
    ]
    assert len(matching) >= 1, (
        f"xlsx_white_text did not fire on fixture 01; got "
        f"{[f.mechanism for f in findings]}"
    )


def test_xlsx_white_text_recovers_payload_into_concealed() -> None:
    fixture = GAUNTLET_DIR / "01_white_cell_text.xlsx"
    findings = detect_xlsx_white_text(fixture)
    assert any(
        f.mechanism == "xlsx_white_text" and _payload_recovered(f.concealed)
        for f in findings
    ), (
        "no xlsx_white_text finding recovered HIDDEN_TEXT_PAYLOAD; "
        f"concealed values: {[f.concealed[:80] for f in findings]}"
    )


def test_xlsx_white_text_clean_on_control() -> None:
    assert CONTROL_FIXTURE.exists(), f"missing control: {CONTROL_FIXTURE}"
    findings = detect_xlsx_white_text(CONTROL_FIXTURE)
    assert all(f.mechanism != "xlsx_white_text" for f in findings), (
        f"xlsx_white_text fired on clean baseline; got {findings}"
    )


# ---------------------------------------------------------------------------
# xlsx_microscopic_font — fixture 02
# ---------------------------------------------------------------------------


def test_xlsx_microscopic_font_catches_fixture_02() -> None:
    fixture = GAUNTLET_DIR / "02_microscopic_font.xlsx"
    assert fixture.exists(), f"missing fixture: {fixture}"
    findings = detect_xlsx_microscopic_font(fixture)
    matching = [
        f for f in findings
        if f.mechanism == "xlsx_microscopic_font" and f.tier == 2
    ]
    assert len(matching) >= 1, (
        f"xlsx_microscopic_font did not fire on fixture 02; got "
        f"{[f.mechanism for f in findings]}"
    )


def test_xlsx_microscopic_font_recovers_payload_into_concealed() -> None:
    fixture = GAUNTLET_DIR / "02_microscopic_font.xlsx"
    findings = detect_xlsx_microscopic_font(fixture)
    assert any(
        f.mechanism == "xlsx_microscopic_font"
        and _payload_recovered(f.concealed)
        for f in findings
    ), (
        "no xlsx_microscopic_font finding recovered the payload; "
        f"concealed values: {[f.concealed[:80] for f in findings]}"
    )


def test_xlsx_microscopic_font_clean_on_control() -> None:
    findings = detect_xlsx_microscopic_font(CONTROL_FIXTURE)
    assert all(
        f.mechanism != "xlsx_microscopic_font" for f in findings
    ), (
        f"xlsx_microscopic_font fired on clean baseline; got {findings}"
    )


# ---------------------------------------------------------------------------
# xlsx_defined_name_payload — fixture 03
# ---------------------------------------------------------------------------


def test_xlsx_defined_name_payload_catches_fixture_03() -> None:
    fixture = GAUNTLET_DIR / "03_defined_name_payload.xlsx"
    assert fixture.exists(), f"missing fixture: {fixture}"
    findings = detect_xlsx_defined_name_payload(fixture)
    matching = [
        f for f in findings
        if f.mechanism == "xlsx_defined_name_payload" and f.tier == 2
    ]
    assert len(matching) >= 1, (
        f"xlsx_defined_name_payload did not fire on fixture 03; got "
        f"{[f.mechanism for f in findings]}"
    )


def test_xlsx_defined_name_payload_recovers_payload_into_concealed() -> None:
    fixture = GAUNTLET_DIR / "03_defined_name_payload.xlsx"
    findings = detect_xlsx_defined_name_payload(fixture)
    assert any(
        f.mechanism == "xlsx_defined_name_payload"
        and _payload_recovered(f.concealed)
        for f in findings
    ), (
        "no xlsx_defined_name_payload finding recovered the payload; "
        f"concealed values: {[f.concealed[:80] for f in findings]}"
    )


def test_xlsx_defined_name_payload_clean_on_control() -> None:
    findings = detect_xlsx_defined_name_payload(CONTROL_FIXTURE)
    assert all(
        f.mechanism != "xlsx_defined_name_payload" for f in findings
    ), (
        f"xlsx_defined_name_payload fired on clean baseline; "
        f"got {findings}"
    )


# ---------------------------------------------------------------------------
# xlsx_comment_payload — fixture 04
# ---------------------------------------------------------------------------


def test_xlsx_comment_payload_catches_fixture_04() -> None:
    fixture = GAUNTLET_DIR / "04_cell_comment.xlsx"
    assert fixture.exists(), f"missing fixture: {fixture}"
    findings = detect_xlsx_comment_payload(fixture)
    matching = [
        f for f in findings
        if f.mechanism == "xlsx_comment_payload" and f.tier == 2
    ]
    assert len(matching) >= 1, (
        f"xlsx_comment_payload did not fire on fixture 04; got "
        f"{[f.mechanism for f in findings]}"
    )


def test_xlsx_comment_payload_recovers_payload_into_concealed() -> None:
    fixture = GAUNTLET_DIR / "04_cell_comment.xlsx"
    findings = detect_xlsx_comment_payload(fixture)
    assert any(
        f.mechanism == "xlsx_comment_payload"
        and _payload_recovered(f.concealed)
        for f in findings
    ), (
        "no xlsx_comment_payload finding recovered the payload; "
        f"concealed values: {[f.concealed[:80] for f in findings]}"
    )


def test_xlsx_comment_payload_clean_on_control() -> None:
    findings = detect_xlsx_comment_payload(CONTROL_FIXTURE)
    assert all(
        f.mechanism != "xlsx_comment_payload" for f in findings
    ), (
        f"xlsx_comment_payload fired on clean baseline; got {findings}"
    )


# ---------------------------------------------------------------------------
# xlsx_metadata_payload — fixture 05
# ---------------------------------------------------------------------------


def test_xlsx_metadata_payload_catches_fixture_05() -> None:
    fixture = GAUNTLET_DIR / "05_custom_xml_properties.xlsx"
    assert fixture.exists(), f"missing fixture: {fixture}"
    findings = detect_xlsx_metadata_payload(fixture)
    matching = [
        f for f in findings
        if f.mechanism == "xlsx_metadata_payload" and f.tier == 1
    ]
    assert len(matching) >= 1, (
        f"xlsx_metadata_payload did not fire on fixture 05; got "
        f"{[f.mechanism for f in findings]}"
    )


def test_xlsx_metadata_payload_recovers_payload_into_concealed() -> None:
    fixture = GAUNTLET_DIR / "05_custom_xml_properties.xlsx"
    findings = detect_xlsx_metadata_payload(fixture)
    assert any(
        f.mechanism == "xlsx_metadata_payload"
        and _payload_recovered(f.concealed)
        for f in findings
    ), (
        "no xlsx_metadata_payload finding recovered the payload; "
        f"concealed values: {[f.concealed[:80] for f in findings]}"
    )


def test_xlsx_metadata_payload_clean_on_control() -> None:
    findings = detect_xlsx_metadata_payload(CONTROL_FIXTURE)
    assert all(
        f.mechanism != "xlsx_metadata_payload" for f in findings
    ), (
        f"xlsx_metadata_payload fired on clean baseline; got {findings}"
    )


# ---------------------------------------------------------------------------
# xlsx_csv_injection_formula — fixture 06
# ---------------------------------------------------------------------------


def test_xlsx_csv_injection_formula_catches_fixture_06() -> None:
    """Fixture 06 carries two payload formulas: a HYPERLINK with
    payload-length display text (Tier 2) and a cmd|... shell-trigger
    (Tier 1). Both must fire from the same mechanism.
    """
    fixture = GAUNTLET_DIR / "06_csv_injection_formula.xlsx"
    assert fixture.exists(), f"missing fixture: {fixture}"
    findings = detect_xlsx_csv_injection_formula(fixture)
    matching = [
        f for f in findings
        if f.mechanism == "xlsx_csv_injection_formula"
    ]
    assert len(matching) >= 2, (
        f"xlsx_csv_injection_formula expected >=2 findings on "
        f"fixture 06 (Tier 1 cmd-pipe + Tier 2 HYPERLINK); got "
        f"{[(f.mechanism, f.tier) for f in findings]}"
    )
    tiers = sorted({f.tier for f in matching})
    assert tiers == [1, 2], (
        f"xlsx_csv_injection_formula on fixture 06: expected both "
        f"Tier 1 and Tier 2 findings; got tiers {tiers}"
    )


def test_xlsx_csv_injection_formula_recovers_payload_into_concealed() -> None:
    """The HYPERLINK display text carries the canonical payload
    marker; verify it is recovered.
    """
    fixture = GAUNTLET_DIR / "06_csv_injection_formula.xlsx"
    findings = detect_xlsx_csv_injection_formula(fixture)
    assert any(
        f.mechanism == "xlsx_csv_injection_formula"
        and _payload_recovered(f.concealed)
        for f in findings
    ), (
        "no xlsx_csv_injection_formula finding recovered the payload; "
        f"concealed values: {[f.concealed[:80] for f in findings]}"
    )


def test_xlsx_csv_injection_formula_clean_on_control() -> None:
    findings = detect_xlsx_csv_injection_formula(CONTROL_FIXTURE)
    assert all(
        f.mechanism != "xlsx_csv_injection_formula" for f in findings
    ), (
        f"xlsx_csv_injection_formula fired on clean baseline; "
        f"got {findings}"
    )


# ---------------------------------------------------------------------------
# Cross-mechanism: each gauntlet fixture closes via exactly one
# v1.1.2 XLSX mechanism. Catches over-firing (a detector reaching
# into a fixture that is meant for a different mechanism).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fixture_filename,expected_mechanism",
    [
        ("01_white_cell_text.xlsx",        "xlsx_white_text"),
        ("02_microscopic_font.xlsx",       "xlsx_microscopic_font"),
        ("03_defined_name_payload.xlsx",   "xlsx_defined_name_payload"),
        ("04_cell_comment.xlsx",           "xlsx_comment_payload"),
        ("05_custom_xml_properties.xlsx",  "xlsx_metadata_payload"),
        ("06_csv_injection_formula.xlsx",  "xlsx_csv_injection_formula"),
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
        "xlsx_white_text": detect_xlsx_white_text,
        "xlsx_microscopic_font": detect_xlsx_microscopic_font,
        "xlsx_defined_name_payload": detect_xlsx_defined_name_payload,
        "xlsx_comment_payload": detect_xlsx_comment_payload,
        "xlsx_metadata_payload": detect_xlsx_metadata_payload,
        "xlsx_csv_injection_formula": detect_xlsx_csv_injection_formula,
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
