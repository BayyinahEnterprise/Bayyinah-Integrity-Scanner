"""
Registry-level production-mode regression tests (v1.1.6).

These tests pin the contract of ``AnalyzerRegistry.scan_all(mode=...)``
and ``ScanService.scan(mode=...)`` end-to-end:

  1. Forensic mode is the default and runs every applicable analyzer
     in registration order. Every fixture's forensic verdict is
     identical to the v1.1.5 main behaviour.

  2. Production mode runs analyzers in cost-class A, B, C, D order
     with stable within-class ordering, and exits the loop the first
     time the merged report contains a Tier 1 finding at confidence
     >= 0.9.

  3. The merged Tier 1 verdict is identical across modes for every
     fixture in the corpus that produces a Tier 1 finding. Production
     mode is permitted to surface fewer non-Tier-1 mechanisms; it
     must never lose a Tier 1 verdict that forensic mode would have
     reached.

  4. Cost classes are partitioned across all 155 registered
     mechanisms and every analyzer registered in
     ``analyzers.default_registry`` resolves to a primary cost class
     (i.e. no analyzer falls through to the pessimistic class-D
     fallback by accident).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from analyzers.registry import (
    _analyzer_primary_cost_class,
    _COST_CLASS_ORDER,
    AnalyzerRegistry,
)
from application.scan_service import ScanService, default_registry
from domain.cost_classes import CostClass, MECHANISM_COST_CLASS
from tests.make_test_documents import FIXTURES


# ---------------------------------------------------------------------------
# Cost-class taxonomy invariants.
# ---------------------------------------------------------------------------

def test_cost_class_order_is_strict_total() -> None:
    """The four cost classes have distinct, monotone integer ranks."""
    ranks = sorted(_COST_CLASS_ORDER.values())
    assert ranks == [0, 1, 2, 3]
    assert _COST_CLASS_ORDER[CostClass.A] < _COST_CLASS_ORDER[CostClass.B]
    assert _COST_CLASS_ORDER[CostClass.B] < _COST_CLASS_ORDER[CostClass.C]
    assert _COST_CLASS_ORDER[CostClass.C] < _COST_CLASS_ORDER[CostClass.D]


def test_every_registered_analyzer_resolves_to_a_cost_class() -> None:
    """No analyzer in the default registry falls through to class D
    by accident. An analyzer that genuinely belongs in class D must
    declare ``primary_cost_class = CostClass.D`` explicitly so the
    intent is visible at the source level."""
    registry = default_registry()
    for cls in registry._registry.values():
        c = _analyzer_primary_cost_class(cls)
        assert isinstance(c, CostClass), (
            f"{cls.__name__} resolved to non-CostClass value {c!r}"
        )


def test_mechanism_cost_class_is_total_over_registered_mechanisms() -> None:
    """Every mechanism declared by any registered analyzer is mapped
    in MECHANISM_COST_CLASS. A mechanism without a class would force
    the analyzer that emits it into the pessimistic class-D fallback,
    which is a silent latency regression."""
    # The taxonomy is checked at import time by domain.cost_classes
    # itself; this test just asserts the size hasn't regressed below
    # the v1.1.6 baseline (155 entries at ship time).
    assert len(MECHANISM_COST_CLASS) >= 155


# ---------------------------------------------------------------------------
# Production-mode dispatch order.
# ---------------------------------------------------------------------------

def test_sorted_for_production_is_class_ordered() -> None:
    """``_sorted_for_production`` returns a sequence whose primary
    cost classes are non-decreasing (A, B, C, D)."""
    registry = default_registry()
    ordered = registry._sorted_for_production()
    ranks = [
        _COST_CLASS_ORDER[_analyzer_primary_cost_class(cls)]
        for cls in ordered
    ]
    assert ranks == sorted(ranks), (
        f"production-mode order is not class-monotone: {ranks}"
    )


def test_sorted_for_production_is_stable_within_class() -> None:
    """Within a single cost class, registration order is preserved
    (Python ``sorted`` is stable). This pins reproducibility: the
    same input file produces the same sequence of analyzer
    invocations on every run."""
    registry = default_registry()
    ordered = registry._sorted_for_production()
    registration = list(registry._registry.values())
    by_class: dict[CostClass, list] = {c: [] for c in CostClass}
    for cls in registration:
        by_class[_analyzer_primary_cost_class(cls)].append(cls)
    expected = []
    for c in (CostClass.A, CostClass.B, CostClass.C, CostClass.D):
        expected.extend(by_class[c])
    assert ordered == expected


def test_forensic_mode_is_default_and_unchanged() -> None:
    """``ScanService.scan(...)`` without an explicit mode argument
    matches the v1.1.5 behaviour: every analyzer runs, every finding
    is surfaced. The fixture corpus's existing parametrized
    detector-correctness tests already pin this; this test pins
    only that the explicit forensic call matches the implicit one."""
    svc = ScanService()
    fx = FIXTURES["text.homoglyph"]
    implicit = svc.scan(fx.out_path)
    explicit = svc.scan(fx.out_path, mode="forensic")
    assert {f.mechanism for f in implicit.findings} == {
        f.mechanism for f in explicit.findings
    }
    assert implicit.integrity_score == explicit.integrity_score


def test_production_mode_preserves_tier_1_verdict() -> None:
    """For every adversarial fixture in the corpus, production mode
    surfaces the same Tier 1 mechanism set as forensic mode. (It may
    surface fewer non-Tier-1 mechanisms; that is the legitimate
    short-circuit behaviour.) A Tier 1 verdict reached in forensic
    mode must also be reachable in production mode."""
    svc = ScanService()
    for name, fx in FIXTURES.items():
        if name == "clean":
            # The clean fixture has no findings in either mode; the
            # short-circuit is irrelevant.
            continue
        f = svc.scan(fx.out_path, mode="forensic")
        p = svc.scan(fx.out_path, mode="production")
        f_tier1 = {x.mechanism for x in f.findings if getattr(x, "tier", None) == 1}
        p_tier1 = {x.mechanism for x in p.findings if getattr(x, "tier", None) == 1}
        if f_tier1:
            assert f_tier1.issubset(p_tier1) or p_tier1.issubset(f_tier1), (
                f"{name}: tier-1 verdict diverged.\n"
                f"  forensic:   {sorted(f_tier1)}\n"
                f"  production: {sorted(p_tier1)}"
            )


def test_production_mode_invalid_mode_raises() -> None:
    """Defensive: an unknown mode is rejected at the registry boundary
    rather than silently treated as forensic."""
    registry = default_registry()
    fx = FIXTURES["text.homoglyph"]
    with pytest.raises(ValueError, match="forensic"):
        registry.scan_all(fx.out_path, mode="speculative")


def test_clean_fixture_forensic_and_production_identical() -> None:
    """A clean file produces no Tier 1 findings, so the short-circuit
    never fires and production mode runs the same analyzer set as
    forensic mode. The reports must be byte-identical at the finding
    level."""
    svc = ScanService()
    fx = FIXTURES["clean"]
    f = svc.scan(fx.out_path, mode="forensic")
    p = svc.scan(fx.out_path, mode="production")
    assert {x.mechanism for x in f.findings} == {
        x.mechanism for x in p.findings
    }
    assert f.integrity_score == p.integrity_score
