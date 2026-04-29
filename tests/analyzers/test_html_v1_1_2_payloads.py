"""
Tests for the six v1.1.2 HTML hidden-text payload detectors.

Each mechanism gets the standard paired-fixture trio per
Differentiator Layer 7:

  - REGISTRY: classified into the right source layer with the
    expected TIER and SEVERITY.
  - CATCH: the matching html_gauntlet fixture produces at least
    one finding from that mechanism.
  - PAYLOAD RECOVERY: the catching finding's ``concealed`` field
    contains the hidden payload bytes (``HIDDEN_TEXT_PAYLOAD`` or
    ``$10,000``), so a reviewer reading the report can read what
    was hidden.
  - CLEAN: the v1.0 baseline clean HTML
    (``tests/fixtures/html/clean/clean.html``) produces zero
    findings from that mechanism.

Mechanism table (matches docs/adversarial/html_gauntlet/REPORT.md):

  | Mechanism                       | Tier | Layer | Sev | Fixture |
  |---------------------------------|------|-------|-----|---------|
  | html_noscript_payload           | 1    | batin | 1.00| 01      |
  | html_template_payload           | 1    | batin | 1.00| 02      |
  | html_comment_payload            | 1    | batin | 1.00| 03      |
  | html_meta_payload               | 1    | batin | 1.00| 04      |
  | html_style_content_payload      | 1    | batin | 1.00| 05      |
  | html_title_text_divergence      | 1    | zahir | 1.00| 06      |
"""
from __future__ import annotations

from pathlib import Path

import pytest

from analyzers.html_noscript_payload import detect_html_noscript_payload
from analyzers.html_template_payload import detect_html_template_payload
from analyzers.html_comment_payload import detect_html_comment_payload
from analyzers.html_meta_payload import detect_html_meta_payload
from analyzers.html_style_content_payload import (
    detect_html_style_content_payload,
)
from analyzers.html_title_text_divergence import (
    detect_html_title_text_divergence,
)
from domain.config import BATIN_MECHANISMS, SEVERITY, TIER, ZAHIR_MECHANISMS


REPO_ROOT = Path(__file__).resolve().parents[2]
GAUNTLET_DIR = REPO_ROOT / "docs/adversarial/html_gauntlet/fixtures"
CONTROL_FIXTURE = REPO_ROOT / "tests/fixtures/html/clean/clean.html"

PAYLOAD_MARKERS = ("HIDDEN_TEXT_PAYLOAD", "$10,000", "10,000", "actual revenue")


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
        ("html_noscript_payload",       "batin", 1, 1.0),
        ("html_template_payload",       "batin", 1, 1.0),
        ("html_comment_payload",        "batin", 1, 1.0),
        ("html_meta_payload",           "batin", 1, 1.0),
        ("html_style_content_payload",  "batin", 1, 1.0),
        ("html_title_text_divergence",  "zahir", 1, 1.0),
    ],
)
def test_v1_1_2_html_mechanism_is_registered(
    mechanism: str,
    layer: str,
    tier_value: int,
    severity_value: float,
) -> None:
    """Every v1.1.2 HTML mechanism is registered in the right layer
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
# html_noscript_payload - fixture 01
# ---------------------------------------------------------------------------


def test_html_noscript_payload_catches_fixture_01() -> None:
    fixture = GAUNTLET_DIR / "01_noscript.html"
    assert fixture.exists(), f"missing fixture: {fixture}"
    findings = list(detect_html_noscript_payload(fixture))
    matching = [
        f for f in findings
        if f.mechanism == "html_noscript_payload" and f.tier == 1
    ]
    assert len(matching) >= 1, (
        f"html_noscript_payload did not fire on fixture 01; got "
        f"{[f.mechanism for f in findings]}"
    )


def test_html_noscript_payload_recovers_payload_into_concealed() -> None:
    fixture = GAUNTLET_DIR / "01_noscript.html"
    findings = list(detect_html_noscript_payload(fixture))
    assert any(
        f.mechanism == "html_noscript_payload"
        and _payload_recovered(f.concealed)
        for f in findings
    ), (
        "no html_noscript_payload finding recovered the payload; "
        f"concealed values: {[f.concealed[:80] for f in findings]}"
    )


def test_html_noscript_payload_clean_on_control() -> None:
    assert CONTROL_FIXTURE.exists(), f"missing control: {CONTROL_FIXTURE}"
    findings = list(detect_html_noscript_payload(CONTROL_FIXTURE))
    assert all(f.mechanism != "html_noscript_payload" for f in findings), (
        f"html_noscript_payload fired on clean baseline; got {findings}"
    )


# ---------------------------------------------------------------------------
# html_template_payload - fixture 02
# ---------------------------------------------------------------------------


def test_html_template_payload_catches_fixture_02() -> None:
    fixture = GAUNTLET_DIR / "02_template.html"
    assert fixture.exists(), f"missing fixture: {fixture}"
    findings = list(detect_html_template_payload(fixture))
    matching = [
        f for f in findings
        if f.mechanism == "html_template_payload" and f.tier == 1
    ]
    assert len(matching) >= 1, (
        f"html_template_payload did not fire on fixture 02; got "
        f"{[f.mechanism for f in findings]}"
    )


def test_html_template_payload_recovers_payload_into_concealed() -> None:
    fixture = GAUNTLET_DIR / "02_template.html"
    findings = list(detect_html_template_payload(fixture))
    assert any(
        f.mechanism == "html_template_payload"
        and _payload_recovered(f.concealed)
        for f in findings
    ), (
        "no html_template_payload finding recovered the payload; "
        f"concealed values: {[f.concealed[:80] for f in findings]}"
    )


def test_html_template_payload_clean_on_control() -> None:
    findings = list(detect_html_template_payload(CONTROL_FIXTURE))
    assert all(f.mechanism != "html_template_payload" for f in findings), (
        f"html_template_payload fired on clean baseline; got {findings}"
    )


# ---------------------------------------------------------------------------
# html_comment_payload - fixture 03
# ---------------------------------------------------------------------------


def test_html_comment_payload_catches_fixture_03() -> None:
    fixture = GAUNTLET_DIR / "03_comment_payload.html"
    assert fixture.exists(), f"missing fixture: {fixture}"
    findings = list(detect_html_comment_payload(fixture))
    matching = [
        f for f in findings
        if f.mechanism == "html_comment_payload" and f.tier == 1
    ]
    assert len(matching) >= 1, (
        f"html_comment_payload did not fire on fixture 03; got "
        f"{[f.mechanism for f in findings]}"
    )


def test_html_comment_payload_recovers_payload_into_concealed() -> None:
    fixture = GAUNTLET_DIR / "03_comment_payload.html"
    findings = list(detect_html_comment_payload(fixture))
    assert any(
        f.mechanism == "html_comment_payload"
        and _payload_recovered(f.concealed)
        for f in findings
    ), (
        "no html_comment_payload finding recovered the payload; "
        f"concealed values: {[f.concealed[:80] for f in findings]}"
    )


def test_html_comment_payload_clean_on_control() -> None:
    findings = list(detect_html_comment_payload(CONTROL_FIXTURE))
    assert all(f.mechanism != "html_comment_payload" for f in findings), (
        f"html_comment_payload fired on clean baseline; got {findings}"
    )


# ---------------------------------------------------------------------------
# html_meta_payload - fixture 04
# ---------------------------------------------------------------------------


def test_html_meta_payload_catches_fixture_04() -> None:
    """Fixture 04 carries the payload in two meta fields (description
    and keywords). Both must fire as html_meta_payload findings.
    """
    fixture = GAUNTLET_DIR / "04_meta_content.html"
    assert fixture.exists(), f"missing fixture: {fixture}"
    findings = list(detect_html_meta_payload(fixture))
    matching = [
        f for f in findings
        if f.mechanism == "html_meta_payload" and f.tier == 1
    ]
    assert len(matching) >= 2, (
        f"html_meta_payload expected >=2 findings on fixture 04 "
        f"(description + keywords); got "
        f"{[(f.mechanism, f.location) for f in findings]}"
    )


def test_html_meta_payload_recovers_payload_into_concealed() -> None:
    fixture = GAUNTLET_DIR / "04_meta_content.html"
    findings = list(detect_html_meta_payload(fixture))
    assert any(
        f.mechanism == "html_meta_payload"
        and _payload_recovered(f.concealed)
        for f in findings
    ), (
        "no html_meta_payload finding recovered the payload; "
        f"concealed values: {[f.concealed[:80] for f in findings]}"
    )


def test_html_meta_payload_clean_on_control() -> None:
    findings = list(detect_html_meta_payload(CONTROL_FIXTURE))
    assert all(f.mechanism != "html_meta_payload" for f in findings), (
        f"html_meta_payload fired on clean baseline; got {findings}"
    )


# ---------------------------------------------------------------------------
# html_style_content_payload - fixture 05
# ---------------------------------------------------------------------------


def test_html_style_content_payload_catches_fixture_05() -> None:
    fixture = GAUNTLET_DIR / "05_css_content.html"
    assert fixture.exists(), f"missing fixture: {fixture}"
    findings = list(detect_html_style_content_payload(fixture))
    matching = [
        f for f in findings
        if f.mechanism == "html_style_content_payload" and f.tier == 1
    ]
    assert len(matching) >= 1, (
        f"html_style_content_payload did not fire on fixture 05; got "
        f"{[f.mechanism for f in findings]}"
    )


def test_html_style_content_payload_recovers_payload_into_concealed() -> None:
    fixture = GAUNTLET_DIR / "05_css_content.html"
    findings = list(detect_html_style_content_payload(fixture))
    assert any(
        f.mechanism == "html_style_content_payload"
        and _payload_recovered(f.concealed)
        for f in findings
    ), (
        "no html_style_content_payload finding recovered the payload; "
        f"concealed values: {[f.concealed[:80] for f in findings]}"
    )


def test_html_style_content_payload_clean_on_control() -> None:
    findings = list(detect_html_style_content_payload(CONTROL_FIXTURE))
    assert all(
        f.mechanism != "html_style_content_payload" for f in findings
    ), (
        f"html_style_content_payload fired on clean baseline; "
        f"got {findings}"
    )


# ---------------------------------------------------------------------------
# html_title_text_divergence - fixture 06
# ---------------------------------------------------------------------------


def test_html_title_text_divergence_catches_fixture_06() -> None:
    fixture = GAUNTLET_DIR / "06_title_payload.html"
    assert fixture.exists(), f"missing fixture: {fixture}"
    findings = list(detect_html_title_text_divergence(fixture))
    matching = [
        f for f in findings
        if f.mechanism == "html_title_text_divergence" and f.tier == 1
    ]
    assert len(matching) >= 1, (
        f"html_title_text_divergence did not fire on fixture 06; got "
        f"{[f.mechanism for f in findings]}"
    )


def test_html_title_text_divergence_recovers_payload_into_concealed() -> None:
    fixture = GAUNTLET_DIR / "06_title_payload.html"
    findings = list(detect_html_title_text_divergence(fixture))
    assert any(
        f.mechanism == "html_title_text_divergence"
        and _payload_recovered(f.concealed)
        for f in findings
    ), (
        "no html_title_text_divergence finding recovered the payload; "
        f"concealed values: {[f.concealed[:80] for f in findings]}"
    )


def test_html_title_text_divergence_clean_on_control() -> None:
    findings = list(detect_html_title_text_divergence(CONTROL_FIXTURE))
    assert all(
        f.mechanism != "html_title_text_divergence" for f in findings
    ), (
        f"html_title_text_divergence fired on clean baseline; "
        f"got {findings}"
    )


# ---------------------------------------------------------------------------
# Cross-mechanism: each gauntlet fixture closes via exactly one
# v1.1.2 HTML mechanism. Catches over-firing (a detector reaching
# into a fixture meant for a different mechanism) and under-firing
# (a detector that misses its own fixture).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fixture_filename,expected_mechanism",
    [
        ("01_noscript.html",         "html_noscript_payload"),
        ("02_template.html",         "html_template_payload"),
        ("03_comment_payload.html",  "html_comment_payload"),
        ("04_meta_content.html",     "html_meta_payload"),
        ("05_css_content.html",      "html_style_content_payload"),
        ("06_title_payload.html",    "html_title_text_divergence"),
    ],
)
def test_each_gauntlet_fixture_closes_via_exactly_one_v1_1_2_mechanism(
    fixture_filename: str,
    expected_mechanism: str,
) -> None:
    """Run all six v1.1.2 detectors against each fixture and confirm
    only the expected mechanism fires. Flags over-firing and
    under-firing.
    """
    fixture = GAUNTLET_DIR / fixture_filename
    assert fixture.exists(), f"missing fixture: {fixture}"

    detectors = {
        "html_noscript_payload":      detect_html_noscript_payload,
        "html_template_payload":      detect_html_template_payload,
        "html_comment_payload":       detect_html_comment_payload,
        "html_meta_payload":          detect_html_meta_payload,
        "html_style_content_payload": detect_html_style_content_payload,
        "html_title_text_divergence": detect_html_title_text_divergence,
    }
    fired: list[str] = []
    for name, fn in detectors.items():
        findings = list(fn(fixture))
        if any(f.mechanism == name for f in findings):
            fired.append(name)
    assert fired == [expected_mechanism], (
        f"fixture {fixture_filename}: expected only "
        f"{expected_mechanism} to fire; instead fired {fired}"
    )
