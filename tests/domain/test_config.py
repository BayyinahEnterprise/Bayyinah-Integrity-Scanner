"""
Tests for domain.config.

These are correctness tests on the constant tables themselves — the
domain layer is only as trustworthy as the values in ``config.py``.
"""

from __future__ import annotations

import pytest

from domain import config


# ---------------------------------------------------------------------------
# Source-layer coverage
# ---------------------------------------------------------------------------

def test_every_severity_mechanism_is_classified_by_source_layer() -> None:
    """Every mechanism with a SEVERITY entry MUST be classified into
    exactly one of ZAHIR_MECHANISMS, BATIN_MECHANISMS, or (v1.1.2)
    ROUTING_MECHANISMS. An unclassified mechanism would default to
    'batin' silently, losing signal."""
    mechanisms = set(config.SEVERITY.keys())
    classified = (
        config.ZAHIR_MECHANISMS
        | config.BATIN_MECHANISMS
        | config.ROUTING_MECHANISMS
    )
    unclassified = mechanisms - classified
    assert not unclassified, (
        f"Mechanisms in SEVERITY but not classified as zahir/batin/"
        f"routing: {unclassified}"
    )


def test_zahir_and_batin_are_disjoint() -> None:
    overlap = config.ZAHIR_MECHANISMS & config.BATIN_MECHANISMS
    assert not overlap, f"Mechanism double-classified as zahir AND batin: {overlap}"


def test_every_severity_mechanism_has_a_tier() -> None:
    sev_keys = set(config.SEVERITY.keys())
    tier_keys = set(config.TIER.keys())
    assert sev_keys == tier_keys, (
        f"SEVERITY and TIER keys disagree. "
        f"Only in SEVERITY: {sev_keys - tier_keys}. "
        f"Only in TIER: {tier_keys - sev_keys}."
    )


# ---------------------------------------------------------------------------
# Value-range invariants
# ---------------------------------------------------------------------------

def test_all_severities_are_in_unit_interval() -> None:
    for mech, sev in config.SEVERITY.items():
        assert 0.0 <= sev <= 1.0, f"{mech} severity {sev} outside [0, 1]"


def test_all_tiers_are_zero_one_two_or_three() -> None:
    """v1.1.2 widens the legal tier set to admit Tier 0 (routing
    transparency). Tier 0 mechanisms live in ROUTING_MECHANISMS."""
    for mech, tier in config.TIER.items():
        assert tier in (0, 1, 2, 3), f"{mech} tier {tier} not in {{0, 1, 2, 3}}"


def test_scan_incomplete_clamp_is_half() -> None:
    """The clamp must be exactly 0.5 — consumers of v0.1 reports have
    been reading this value since the patch landed."""
    assert config.SCAN_INCOMPLETE_CLAMP == 0.5


def test_tool_identity_matches_v0_1() -> None:
    """IntegrityReport.to_dict emits these values verbatim. A drift
    here would break byte-identical parity with v0.1."""
    assert config.TOOL_NAME == "bayyinah"
    assert config.TOOL_VERSION == "0.1.0"


def test_tier_legend_has_three_entries_keyed_as_strings() -> None:
    assert set(config.TIER_LEGEND.keys()) == {"1", "2", "3"}
    for v in config.TIER_LEGEND.values():
        assert isinstance(v, str) and v


def test_verdict_disclaimer_is_the_v01_string() -> None:
    """The disclaimer is serialised verbatim; altering it breaks parity."""
    assert (
        config.VERDICT_DISCLAIMER
        == "This report presents observed mechanisms and their validity "
           "tiers. It does NOT self-validate a moral or malicious "
           "verdict. The scanner makes the invisible visible; the "
           "reader performs the recognition."
    )


# ---------------------------------------------------------------------------
# Unicode tables
# ---------------------------------------------------------------------------

def test_zero_width_set_includes_canonical_codepoints() -> None:
    for c in ("\u200B", "\u200C", "\u200D", "\u2060", "\uFEFF"):
        assert c in config.ZERO_WIDTH_CHARS


def test_bidi_control_set_includes_rlo_and_isolates() -> None:
    assert "\u202E" in config.BIDI_CONTROL_CHARS   # RLO — classic attack
    assert "\u2068" in config.BIDI_CONTROL_CHARS   # FSI


def test_tag_char_range_covers_e0000_block() -> None:
    assert 0xE0000 in config.TAG_CHAR_RANGE
    assert 0xE007F in config.TAG_CHAR_RANGE
    assert 0xE0080 not in config.TAG_CHAR_RANGE


def test_confusable_map_points_to_single_latin_glyphs() -> None:
    for src, tgt in config.CONFUSABLE_TO_LATIN.items():
        assert len(src) == 1, f"Confusable source {src!r} must be a single codepoint"
        assert len(tgt) == 1 and tgt.isascii(), (
            f"Confusable target {tgt!r} must be single ASCII glyph"
        )


# ---------------------------------------------------------------------------
# Physics thresholds
# ---------------------------------------------------------------------------

def test_invisible_render_mode_is_three() -> None:
    assert config.INVISIBLE_RENDER_MODE == 3


def test_contrast_thresholds_are_sensible() -> None:
    assert 0.0 < config.COLOR_CONTRAST_THRESHOLD < 1.0
    assert 0.0 < config.SPAN_OVERLAP_THRESHOLD <= 1.0
    assert config.MICROSCOPIC_FONT_THRESHOLD > 0


# ---------------------------------------------------------------------------
# Verdict enumeration
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "label",
    ["sahih", "mushtabih", "mukhfi", "munafiq", "mughlaq"],
)
def test_every_verdict_label_is_exposed(label: str) -> None:
    exposed = {
        config.VERDICT_SAHIH,
        config.VERDICT_MUSHTABIH,
        config.VERDICT_MUKHFI,
        config.VERDICT_MUNAFIQ,
        config.VERDICT_MUGHLAQ,
    }
    assert label in exposed
