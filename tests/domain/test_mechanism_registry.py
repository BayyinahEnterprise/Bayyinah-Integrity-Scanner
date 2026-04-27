"""
Tests for ``domain.config.MECHANISM_REGISTRY``.

The registry is the single auditable union of every mechanism Bayyinah
emits. Three properties are pinned:

  1. The count is exact (108 at v1.1) — anyone who reads the public
     docs and counts can verify the number with a single import.
  2. The registry is the union of ZAHIR_MECHANISMS and BATIN_MECHANISMS,
     and the two source-layer sets are disjoint.
  3. The SEVERITY and TIER tables are coherent with the registry —
     every mechanism has both, and no orphan severity / tier entries
     exist for nonexistent mechanisms.

The strongest claim is property 3: the same coherence the
``domain/config.py`` module enforces at import time is also asserted
by the test suite, so a regression that bypasses the import-time check
(by, say, deleting the assertion line) is still caught here.
"""

from __future__ import annotations

import pytest

from domain.config import (
    BATIN_MECHANISMS,
    MECHANISM_REGISTRY,
    SEVERITY,
    TIER,
    ZAHIR_MECHANISMS,
)
from domain.config import ROUTING_MECHANISMS


def test_registry_is_frozenset() -> None:
    assert isinstance(MECHANISM_REGISTRY, frozenset)


def test_registry_count_is_exact_111() -> None:
    """Pin the count. Adding a mechanism must update this number;
    that is itself a structural reminder to update SEVERITY + TIER +
    the source-layer set in the same commit.

    v1.1.2 Day 1 raised the count from 108 (27 zahir + 81 batin) to
    109 with the addition of format_routing_divergence in
    ROUTING_MECHANISMS. Day 2 mechanism 03 (pdf_off_page_text, zahir)
    raised it to 110. Day 2 mechanism 04 (pdf_metadata_analyzer,
    batin) raises it to 111 (28 zahir + 82 batin + 1 routing).
    pdf_metadata_analyzer classifies as batin because the /Info
    dictionary and XMP stream live in the document's inner object
    graph, not the rendered surface."""
    assert len(MECHANISM_REGISTRY) == 111, (
        f"Mechanism count drift: expected 111 "
        f"(28 zahir + 82 batin + 1 routing), "
        f"got {len(MECHANISM_REGISTRY)} "
        f"(zahir={len(ZAHIR_MECHANISMS)}, batin={len(BATIN_MECHANISMS)}, "
        f"routing={len(ROUTING_MECHANISMS)})"
    )


def test_zahir_count_is_exact_28() -> None:
    """v1.1.2 Day 2 mechanism 03 (pdf_off_page_text) added a zahir
    entry; the count moves from 27 to 28."""
    assert len(ZAHIR_MECHANISMS) == 28


def test_batin_count_is_exact_82() -> None:
    """v1.1.2 Day 2 mechanism 04 (pdf_metadata_analyzer) classifies
    as batin because /Info and XMP signals live in the document's
    inner object graph; the count moves from 81 (v1.0 baseline) to
    82."""
    assert len(BATIN_MECHANISMS) == 82


def test_registry_is_union_of_zahir_batin_and_routing() -> None:
    """v1.1.2 - the registry is the union of three layers:
    ZAHIR_MECHANISMS, BATIN_MECHANISMS, ROUTING_MECHANISMS."""
    assert MECHANISM_REGISTRY == (
        ZAHIR_MECHANISMS | BATIN_MECHANISMS | ROUTING_MECHANISMS
    )


def test_zahir_batin_and_routing_are_pairwise_disjoint() -> None:
    """Every mechanism belongs to exactly one source layer."""
    zb = ZAHIR_MECHANISMS & BATIN_MECHANISMS
    zr = ZAHIR_MECHANISMS & ROUTING_MECHANISMS
    br = BATIN_MECHANISMS & ROUTING_MECHANISMS
    assert zb == set(), f"Mechanisms in both ZAHIR and BATIN: {sorted(zb)}"
    assert zr == set(), f"Mechanisms in both ZAHIR and ROUTING: {sorted(zr)}"
    assert br == set(), f"Mechanisms in both BATIN and ROUTING: {sorted(br)}"


def test_severity_keys_match_registry() -> None:
    """Every mechanism has a SEVERITY entry; no orphan entries."""
    sev_keys = set(SEVERITY.keys())
    missing = MECHANISM_REGISTRY - sev_keys
    orphan = sev_keys - MECHANISM_REGISTRY
    assert not missing, f"Mechanisms without SEVERITY: {sorted(missing)}"
    assert not orphan, f"Orphan SEVERITY entries: {sorted(orphan)}"


def test_tier_keys_match_registry() -> None:
    """Every mechanism has a TIER entry; no orphan entries."""
    tier_keys = set(TIER.keys())
    missing = MECHANISM_REGISTRY - tier_keys
    orphan = tier_keys - MECHANISM_REGISTRY
    assert not missing, f"Mechanisms without TIER: {sorted(missing)}"
    assert not orphan, f"Orphan TIER entries: {sorted(orphan)}"


def test_every_severity_value_in_unit_interval() -> None:
    for mech, sev in SEVERITY.items():
        assert 0.0 <= sev <= 1.0, (
            f"Severity out of [0,1] range for {mech!r}: {sev}"
        )


def test_every_tier_value_is_zero_one_two_or_three() -> None:
    """v1.1.2 - tier 0 (routing transparency) is now legal for
    mechanisms in ROUTING_MECHANISMS. Tiers 1/2/3 remain the legal
    set for ZAHIR/BATIN concealment mechanisms."""
    for mech, tier in TIER.items():
        assert tier in (0, 1, 2, 3), (
            f"Tier out of {{0,1,2,3}} for {mech!r}: {tier}"
        )
        if tier == 0:
            assert mech in ROUTING_MECHANISMS, (
                f"Tier 0 found on non-routing mechanism {mech!r} - "
                f"Tier 0 is reserved for ROUTING_MECHANISMS"
            )


def test_registry_exposed_via_bayyinah_top_level() -> None:
    """The reviewer's load-bearing usage pattern must work:

        >>> from bayyinah import MECHANISM_REGISTRY

    The registry is part of the additive-only public surface
    (declared in ``bayyinah.__all__`` and asserted by the CI workflow).
    """
    import bayyinah
    assert "MECHANISM_REGISTRY" in bayyinah.__all__
    assert hasattr(bayyinah, "MECHANISM_REGISTRY")
    assert bayyinah.MECHANISM_REGISTRY is MECHANISM_REGISTRY
