"""
Tests for domain.finding.Finding.

Coverage targets:
  * shape parity with v0/v0.1 (same fields, same defaults)
  * source_layer inference from mechanism name
  * source_layer is EXCLUDED from to_dict() — this is the parity
    invariant Phase 1 absolutely must preserve
  * __post_init__ validation for tier, confidence, source_layer
  * severity_override precedence over the SEVERITY table
  * byte-identical to_dict output vs. bayyinah_v0_1.Finding
"""

from __future__ import annotations

import json

import pytest

import bayyinah_v0_1
from domain.config import SEVERITY
from domain.exceptions import InvalidFindingError
from domain.finding import Finding


# ---------------------------------------------------------------------------
# Construction & defaults
# ---------------------------------------------------------------------------

def test_minimal_construction() -> None:
    f = Finding(
        mechanism="zero_width_chars",
        tier=2,
        confidence=0.9,
        description="d",
        location="page 1",
    )
    assert f.mechanism == "zero_width_chars"
    assert f.tier == 2
    assert f.confidence == 0.9
    assert f.surface == ""
    assert f.concealed == ""
    assert f.severity_override is None


# ---------------------------------------------------------------------------
# source_layer inference
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "mechanism",
    [
        "invisible_render_mode", "white_on_white_text", "microscopic_font",
        "off_page_text", "zero_width_chars", "bidi_control", "tag_chars",
        "overlapping_text", "homoglyph",
    ],
)
def test_zahir_mechanisms_infer_zahir(mechanism: str) -> None:
    f = Finding(mechanism=mechanism, tier=2, confidence=0.9,
                description="d", location="loc")
    assert f.source_layer == "zahir"


@pytest.mark.parametrize(
    "mechanism",
    [
        "javascript", "openaction", "additional_actions", "launch_action",
        "embedded_file", "file_attachment_annot", "incremental_update",
        "metadata_anomaly", "hidden_ocg", "tounicode_anomaly", "scan_error",
    ],
)
def test_batin_mechanisms_infer_batin(mechanism: str) -> None:
    f = Finding(mechanism=mechanism, tier=2, confidence=0.9,
                description="d", location="loc")
    assert f.source_layer == "batin"


def test_unknown_mechanism_defaults_to_batin() -> None:
    """An unknown mechanism name is treated as batin — the safer
    classification; the reader sees the unclassified mechanism as
    structural suspicion rather than silently rendered in the surface
    bucket."""
    f = Finding(mechanism="not_a_real_mechanism", tier=3, confidence=0.1,
                description="d", location="loc")
    assert f.source_layer == "batin"


def test_explicit_source_layer_overrides_inference() -> None:
    f = Finding(mechanism="javascript", tier=1, confidence=1.0,
                description="d", location="loc",
                source_layer="zahir")  # override the batin inference
    assert f.source_layer == "zahir"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad_tier", [0, 4, -1, 2.5, "1", None])
def test_invalid_tier_raises(bad_tier) -> None:
    with pytest.raises(InvalidFindingError):
        Finding(mechanism="zero_width_chars", tier=bad_tier,  # type: ignore[arg-type]
                confidence=0.9, description="d", location="l")


@pytest.mark.parametrize("bad_conf", [-0.01, 1.01, 2.0, "0.5", None])
def test_invalid_confidence_raises(bad_conf) -> None:
    with pytest.raises(InvalidFindingError):
        Finding(mechanism="zero_width_chars", tier=2,
                confidence=bad_conf,  # type: ignore[arg-type]
                description="d", location="l")


def test_invalid_source_layer_raises() -> None:
    with pytest.raises(InvalidFindingError):
        Finding(mechanism="zero_width_chars", tier=2, confidence=0.9,
                description="d", location="l",
                source_layer="zahir_batin")  # type: ignore[arg-type]


def test_invalid_severity_override_raises() -> None:
    with pytest.raises(InvalidFindingError):
        Finding(mechanism="zero_width_chars", tier=2, confidence=0.9,
                description="d", location="l",
                severity_override=1.5)


def test_empty_mechanism_raises() -> None:
    with pytest.raises(InvalidFindingError):
        Finding(mechanism="", tier=2, confidence=0.9,
                description="d", location="l")


# ---------------------------------------------------------------------------
# Severity resolution
# ---------------------------------------------------------------------------

def test_severity_reads_from_table() -> None:
    f = Finding(mechanism="javascript", tier=1, confidence=1.0,
                description="d", location="l")
    assert f.severity == SEVERITY["javascript"] == 0.30


def test_severity_override_wins() -> None:
    f = Finding(mechanism="javascript", tier=1, confidence=1.0,
                description="d", location="l", severity_override=0.05)
    assert f.severity == 0.05


def test_unknown_mechanism_defaults_severity_to_0_05() -> None:
    f = Finding(mechanism="not_a_real_mechanism", tier=3, confidence=0.5,
                description="d", location="l")
    assert f.severity == 0.05


# ---------------------------------------------------------------------------
# to_dict — byte-identical to bayyinah_v0_1.Finding
# ---------------------------------------------------------------------------

def test_to_dict_does_not_leak_source_layer() -> None:
    """Absolutely critical: source_layer is an internal methodological
    field. Emitting it would break the v0/v0.1 parity invariant asserted
    by tests/test_fixtures.py::test_v0_v01_parity."""
    f = Finding(mechanism="homoglyph", tier=2, confidence=0.8,
                description="d", location="page 1", surface="Hello",
                concealed="Hеllо")
    d = f.to_dict()
    assert "source_layer" not in d
    assert "source_layer" not in d.get("inversion_recovery", {})


def test_to_dict_keys_match_v01() -> None:
    domain_f = Finding(mechanism="homoglyph", tier=2, confidence=0.8,
                       description="d", location="loc",
                       surface="Hello", concealed="Hеllо")
    v01_f = bayyinah_v0_1.Finding(
        mechanism="homoglyph", tier=2, confidence=0.8,
        description="d", location="loc",
        surface="Hello", concealed="Hеllо",
    )
    assert list(domain_f.to_dict().keys()) == list(v01_f.to_dict().keys())


def test_to_dict_byte_identical_to_v01() -> None:
    """Serialised output must match v0.1 byte-for-byte. This is the
    additive-only invariant: domain.Finding.to_dict is the v0.1 shape."""
    kwargs = dict(
        mechanism="zero_width_chars",
        tier=2,
        confidence=0.875,  # Non-trivial to force the round() to bite
        description="found ZWSP in rendered text",
        location="page 2, span 5",
        surface="Hello",
        concealed="H\u200Be\u200Bl\u200Bl\u200Bo",
    )
    domain_json = json.dumps(Finding(**kwargs).to_dict(), sort_keys=True)
    v01_json = json.dumps(bayyinah_v0_1.Finding(**kwargs).to_dict(), sort_keys=True)
    assert domain_json == v01_json


def test_severity_override_propagates_through_to_dict() -> None:
    f = Finding(mechanism="scan_error", tier=3, confidence=1.0,
                description="d", location="l", severity_override=0.0)
    assert f.to_dict()["severity"] == 0.0


def test_confidence_is_rounded_to_three_places_in_to_dict() -> None:
    """v0.1 rounds confidence to 3 decimal places in to_dict — mirror it."""
    f = Finding(mechanism="homoglyph", tier=2, confidence=0.123456789,
                description="d", location="l")
    assert f.to_dict()["confidence"] == 0.123
