"""
Tests for the six v1.1.2 EML hidden-text / hidden-identity detectors.

Each mechanism gets the standard paired-fixture trio per
Differentiator Layer 7:

  - REGISTRY: classified into the right source layer with the
    expected TIER and SEVERITY.
  - CATCH: the matching eml_gauntlet fixture produces at least
    one finding from that mechanism.
  - PAYLOAD RECOVERY: the catching finding's ``concealed`` field
    contains the canonical payload marker - either a hidden-text
    marker (``HIDDEN_TEXT_PAYLOAD`` / ``$10,000`` /
    ``actual revenue``) or a hidden-identity marker
    (``attacker-controlled`` / ``attacker-bulk`` /
    ``attacker.example``). The EML gauntlet has both shapes:
    fixtures 04/05/06 hide text, fixtures 01/02/03 hide routing
    identity.
  - CLEAN: the clean baseline EML fixtures
    (``tests/fixtures/eml/clean/plain.eml``,
    ``multipart_equivalent.eml``) produce zero findings from that
    mechanism.

Mechanism table (matches docs/adversarial/eml_gauntlet/REPORT.md):

  | Mechanism                          | Tier | Layer | Sev  | Fixture |
  |------------------------------------|------|-------|------|---------|
  | eml_from_replyto_mismatch          | 2    | zahir | 0.25 | 01      |
  | eml_returnpath_from_mismatch       | 2    | batin | 0.25 | 02      |
  | eml_received_chain_anomaly         | 2    | batin | 0.20 | 03      |
  | eml_base64_text_part               | 1    | zahir | 0.20 | 04      |
  | eml_header_continuation_payload    | 1    | batin | 0.15 | 05      |
  | eml_xheader_payload                | 1    | batin | 0.15 | 06      |
"""
from __future__ import annotations

from pathlib import Path

import pytest

from analyzers.eml_from_replyto_mismatch import detect_eml_from_replyto_mismatch
from analyzers.eml_returnpath_from_mismatch import (
    detect_eml_returnpath_from_mismatch,
)
from analyzers.eml_received_chain_anomaly import detect_eml_received_chain_anomaly
from analyzers.eml_base64_text_part import detect_eml_base64_text_part
from analyzers.eml_header_continuation_payload import (
    detect_eml_header_continuation_payload,
)
from analyzers.eml_xheader_payload import detect_eml_xheader_payload
from domain.config import BATIN_MECHANISMS, SEVERITY, TIER, ZAHIR_MECHANISMS


REPO_ROOT = Path(__file__).resolve().parents[2]
GAUNTLET_DIR = REPO_ROOT / "docs/adversarial/eml_gauntlet/fixtures"
CLEAN_DIR = REPO_ROOT / "tests/fixtures/eml/clean"
CLEAN_FIXTURES = (
    CLEAN_DIR / "plain.eml",
    CLEAN_DIR / "multipart_equivalent.eml",
)

HIDDEN_TEXT_MARKERS = ("HIDDEN_TEXT_PAYLOAD", "$10,000", "10,000", "actual revenue")
HIDDEN_IDENTITY_MARKERS = (
    "attacker-controlled",
    "attacker-bulk",
    "attacker.example",
)
ALL_PAYLOAD_MARKERS = HIDDEN_TEXT_MARKERS + HIDDEN_IDENTITY_MARKERS


def _payload_recovered(concealed: str) -> bool:
    """Return True when the concealed string contains any canonical
    payload marker (hidden-text or hidden-identity).
    """
    return any(marker in concealed for marker in ALL_PAYLOAD_MARKERS)


# ---------------------------------------------------------------------------
# Registry checks
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "mechanism,layer,tier_value,severity_value",
    [
        ("eml_from_replyto_mismatch",       "zahir", 2, 0.25),
        ("eml_returnpath_from_mismatch",    "batin", 2, 0.25),
        ("eml_received_chain_anomaly",      "batin", 2, 0.20),
        ("eml_base64_text_part",            "zahir", 1, 0.20),
        ("eml_header_continuation_payload", "batin", 1, 0.15),
        ("eml_xheader_payload",             "batin", 1, 0.15),
    ],
)
def test_v1_1_2_eml_mechanism_is_registered(
    mechanism: str,
    layer: str,
    tier_value: int,
    severity_value: float,
) -> None:
    """Every v1.1.2 EML mechanism is registered in the right layer
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
# eml_from_replyto_mismatch - fixture 01
# ---------------------------------------------------------------------------


def test_eml_from_replyto_mismatch_catches_fixture_01() -> None:
    fixture = GAUNTLET_DIR / "01_from_replyto_mismatch.eml"
    assert fixture.exists(), f"missing fixture: {fixture}"
    findings = list(detect_eml_from_replyto_mismatch(fixture))
    matching = [
        f for f in findings
        if f.mechanism == "eml_from_replyto_mismatch" and f.tier == 2
    ]
    assert len(matching) >= 1, (
        f"eml_from_replyto_mismatch did not fire on fixture 01; got "
        f"{[f.mechanism for f in findings]}"
    )


def test_eml_from_replyto_mismatch_recovers_payload_into_concealed() -> None:
    fixture = GAUNTLET_DIR / "01_from_replyto_mismatch.eml"
    findings = list(detect_eml_from_replyto_mismatch(fixture))
    assert any(
        f.mechanism == "eml_from_replyto_mismatch"
        and _payload_recovered(f.concealed)
        for f in findings
    ), (
        "no eml_from_replyto_mismatch finding recovered the concealed "
        "Reply-To target; concealed values: "
        f"{[f.concealed[:80] for f in findings]}"
    )


def test_eml_from_replyto_mismatch_clean_on_controls() -> None:
    for control in CLEAN_FIXTURES:
        assert control.exists(), f"missing control: {control}"
        findings = list(detect_eml_from_replyto_mismatch(control))
        assert all(
            f.mechanism != "eml_from_replyto_mismatch" for f in findings
        ), (
            f"eml_from_replyto_mismatch fired on clean baseline "
            f"{control.name}; got {findings}"
        )


# ---------------------------------------------------------------------------
# eml_returnpath_from_mismatch - fixture 02
# ---------------------------------------------------------------------------


def test_eml_returnpath_from_mismatch_catches_fixture_02() -> None:
    fixture = GAUNTLET_DIR / "02_returnpath_mismatch.eml"
    assert fixture.exists(), f"missing fixture: {fixture}"
    findings = list(detect_eml_returnpath_from_mismatch(fixture))
    matching = [
        f for f in findings
        if f.mechanism == "eml_returnpath_from_mismatch" and f.tier == 2
    ]
    assert len(matching) >= 1, (
        f"eml_returnpath_from_mismatch did not fire on fixture 02; got "
        f"{[f.mechanism for f in findings]}"
    )


def test_eml_returnpath_from_mismatch_recovers_payload_into_concealed() -> None:
    fixture = GAUNTLET_DIR / "02_returnpath_mismatch.eml"
    findings = list(detect_eml_returnpath_from_mismatch(fixture))
    assert any(
        f.mechanism == "eml_returnpath_from_mismatch"
        and _payload_recovered(f.concealed)
        for f in findings
    ), (
        "no eml_returnpath_from_mismatch finding recovered the concealed "
        "Return-Path target; concealed values: "
        f"{[f.concealed[:80] for f in findings]}"
    )


def test_eml_returnpath_from_mismatch_clean_on_controls() -> None:
    for control in CLEAN_FIXTURES:
        findings = list(detect_eml_returnpath_from_mismatch(control))
        assert all(
            f.mechanism != "eml_returnpath_from_mismatch" for f in findings
        ), (
            f"eml_returnpath_from_mismatch fired on clean baseline "
            f"{control.name}; got {findings}"
        )


# ---------------------------------------------------------------------------
# eml_received_chain_anomaly - fixture 03
# ---------------------------------------------------------------------------


def test_eml_received_chain_anomaly_catches_fixture_03() -> None:
    fixture = GAUNTLET_DIR / "03_received_chain_anomaly.eml"
    assert fixture.exists(), f"missing fixture: {fixture}"
    findings = list(detect_eml_received_chain_anomaly(fixture))
    matching = [
        f for f in findings
        if f.mechanism == "eml_received_chain_anomaly" and f.tier == 2
    ]
    assert len(matching) >= 1, (
        f"eml_received_chain_anomaly did not fire on fixture 03; got "
        f"{[f.mechanism for f in findings]}"
    )


def test_eml_received_chain_anomaly_recovers_payload_into_concealed() -> None:
    fixture = GAUNTLET_DIR / "03_received_chain_anomaly.eml"
    findings = list(detect_eml_received_chain_anomaly(fixture))
    assert any(
        f.mechanism == "eml_received_chain_anomaly"
        and _payload_recovered(f.concealed)
        for f in findings
    ), (
        "no eml_received_chain_anomaly finding recovered the concealed "
        "relay chain; concealed values: "
        f"{[f.concealed[:80] for f in findings]}"
    )


def test_eml_received_chain_anomaly_clean_on_controls() -> None:
    for control in CLEAN_FIXTURES:
        findings = list(detect_eml_received_chain_anomaly(control))
        assert all(
            f.mechanism != "eml_received_chain_anomaly" for f in findings
        ), (
            f"eml_received_chain_anomaly fired on clean baseline "
            f"{control.name}; got {findings}"
        )


# ---------------------------------------------------------------------------
# eml_base64_text_part - fixture 04
# ---------------------------------------------------------------------------


def test_eml_base64_text_part_catches_fixture_04() -> None:
    fixture = GAUNTLET_DIR / "04_base64_body_payload.eml"
    assert fixture.exists(), f"missing fixture: {fixture}"
    findings = list(detect_eml_base64_text_part(fixture))
    matching = [
        f for f in findings
        if f.mechanism == "eml_base64_text_part" and f.tier == 1
    ]
    assert len(matching) >= 1, (
        f"eml_base64_text_part did not fire on fixture 04; got "
        f"{[f.mechanism for f in findings]}"
    )


def test_eml_base64_text_part_recovers_payload_into_concealed() -> None:
    fixture = GAUNTLET_DIR / "04_base64_body_payload.eml"
    findings = list(detect_eml_base64_text_part(fixture))
    assert any(
        f.mechanism == "eml_base64_text_part"
        and _payload_recovered(f.concealed)
        for f in findings
    ), (
        "no eml_base64_text_part finding recovered the decoded payload; "
        f"concealed values: {[f.concealed[:80] for f in findings]}"
    )


def test_eml_base64_text_part_clean_on_controls() -> None:
    for control in CLEAN_FIXTURES:
        findings = list(detect_eml_base64_text_part(control))
        assert all(
            f.mechanism != "eml_base64_text_part" for f in findings
        ), (
            f"eml_base64_text_part fired on clean baseline "
            f"{control.name}; got {findings}"
        )


# ---------------------------------------------------------------------------
# eml_header_continuation_payload - fixture 05
# ---------------------------------------------------------------------------


def test_eml_header_continuation_payload_catches_fixture_05() -> None:
    fixture = GAUNTLET_DIR / "05_header_continuation_smuggle.eml"
    assert fixture.exists(), f"missing fixture: {fixture}"
    findings = list(detect_eml_header_continuation_payload(fixture))
    matching = [
        f for f in findings
        if f.mechanism == "eml_header_continuation_payload" and f.tier == 1
    ]
    assert len(matching) >= 1, (
        f"eml_header_continuation_payload did not fire on fixture 05; got "
        f"{[f.mechanism for f in findings]}"
    )


def test_eml_header_continuation_payload_recovers_payload() -> None:
    fixture = GAUNTLET_DIR / "05_header_continuation_smuggle.eml"
    findings = list(detect_eml_header_continuation_payload(fixture))
    assert any(
        f.mechanism == "eml_header_continuation_payload"
        and _payload_recovered(f.concealed)
        for f in findings
    ), (
        "no eml_header_continuation_payload finding recovered the "
        f"unfolded payload; concealed values: "
        f"{[f.concealed[:80] for f in findings]}"
    )


def test_eml_header_continuation_payload_clean_on_controls() -> None:
    for control in CLEAN_FIXTURES:
        findings = list(detect_eml_header_continuation_payload(control))
        assert all(
            f.mechanism != "eml_header_continuation_payload" for f in findings
        ), (
            f"eml_header_continuation_payload fired on clean baseline "
            f"{control.name}; got {findings}"
        )


# ---------------------------------------------------------------------------
# eml_xheader_payload - fixture 06
# ---------------------------------------------------------------------------


def test_eml_xheader_payload_catches_fixture_06() -> None:
    fixture = GAUNTLET_DIR / "06_long_xheader_payload.eml"
    assert fixture.exists(), f"missing fixture: {fixture}"
    findings = list(detect_eml_xheader_payload(fixture))
    matching = [
        f for f in findings
        if f.mechanism == "eml_xheader_payload" and f.tier == 1
    ]
    assert len(matching) >= 1, (
        f"eml_xheader_payload did not fire on fixture 06; got "
        f"{[f.mechanism for f in findings]}"
    )


def test_eml_xheader_payload_recovers_payload_into_concealed() -> None:
    fixture = GAUNTLET_DIR / "06_long_xheader_payload.eml"
    findings = list(detect_eml_xheader_payload(fixture))
    assert any(
        f.mechanism == "eml_xheader_payload"
        and _payload_recovered(f.concealed)
        for f in findings
    ), (
        "no eml_xheader_payload finding recovered the long X-* header "
        f"value; concealed values: {[f.concealed[:80] for f in findings]}"
    )


def test_eml_xheader_payload_clean_on_controls() -> None:
    for control in CLEAN_FIXTURES:
        findings = list(detect_eml_xheader_payload(control))
        assert all(
            f.mechanism != "eml_xheader_payload" for f in findings
        ), (
            f"eml_xheader_payload fired on clean baseline "
            f"{control.name}; got {findings}"
        )


# ---------------------------------------------------------------------------
# Cross-mechanism over-firing checks
# ---------------------------------------------------------------------------
#
# Each detector should only fire on its target fixture (or fixtures
# that share its structural shape). The cross-matrix below pins the
# target-fixture-only contract for every mechanism.


@pytest.mark.parametrize(
    "detector,target_fixture",
    [
        (detect_eml_from_replyto_mismatch,       "01_from_replyto_mismatch.eml"),
        (detect_eml_returnpath_from_mismatch,    "02_returnpath_mismatch.eml"),
        (detect_eml_received_chain_anomaly,      "03_received_chain_anomaly.eml"),
        (detect_eml_base64_text_part,            "04_base64_body_payload.eml"),
        (detect_eml_header_continuation_payload, "05_header_continuation_smuggle.eml"),
    ],
)
def test_v1_1_2_eml_detectors_target_their_fixtures(
    detector,
    target_fixture: str,
) -> None:
    """Each detector except eml_xheader_payload fires on exactly its
    target fixture among the six gauntlet fixtures.

    eml_xheader_payload is excluded from this strict-targeting check
    because fixture 05's folded continuation header is also an X-*
    header whose unfolded value is long - both eml_xheader_payload and
    eml_header_continuation_payload legitimately fire there. They
    surface distinct structural shapes (heavy fold count vs. long
    unfolded length) and the multi-finding outcome is the right
    behaviour.
    """
    target_path = GAUNTLET_DIR / target_fixture
    target_findings = list(detector(target_path))
    assert any(
        f.mechanism == detector.__name__.replace("detect_", "")
        for f in target_findings
    ), f"{detector.__name__} missed its target fixture {target_fixture}"

    other_fixtures = [
        f for f in sorted(GAUNTLET_DIR.glob("*.eml")) if f.name != target_fixture
    ]
    for other in other_fixtures:
        other_findings = list(detector(other))
        own_mech = detector.__name__.replace("detect_", "")
        assert all(f.mechanism != own_mech for f in other_findings), (
            f"{detector.__name__} over-fired on non-target {other.name}; "
            f"got {[f.mechanism for f in other_findings]}"
        )


def test_eml_xheader_payload_target_with_continuation_overlap() -> None:
    """eml_xheader_payload must fire on its primary target (06) AND
    may legitimately also fire on fixture 05 (whose folded X-Custom-
    Note is an X-* header of long unfolded length). It must NOT fire
    on fixtures 01-04.
    """
    must_fire = (
        GAUNTLET_DIR / "06_long_xheader_payload.eml",
        GAUNTLET_DIR / "05_header_continuation_smuggle.eml",
    )
    must_not_fire = (
        GAUNTLET_DIR / "01_from_replyto_mismatch.eml",
        GAUNTLET_DIR / "02_returnpath_mismatch.eml",
        GAUNTLET_DIR / "03_received_chain_anomaly.eml",
        GAUNTLET_DIR / "04_base64_body_payload.eml",
    )
    for fix in must_fire:
        findings = list(detect_eml_xheader_payload(fix))
        assert any(
            f.mechanism == "eml_xheader_payload" for f in findings
        ), f"eml_xheader_payload missed expected fire on {fix.name}"
    for fix in must_not_fire:
        findings = list(detect_eml_xheader_payload(fix))
        assert all(
            f.mechanism != "eml_xheader_payload" for f in findings
        ), (
            f"eml_xheader_payload over-fired on {fix.name}; "
            f"got {[f.mechanism for f in findings]}"
        )
