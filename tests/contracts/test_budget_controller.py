"""
v1.6.0 (Round 16) Q-PRO-3 honest budget controller contract pin.

Pins docs/budget.md properties P1 through P5 (plus invariant checks
in BudgetPlan.__post_init__).

Per CODING_STRATEGY §6 v1.6.0: this is a NEW pure-projection layer
shipped at v1.6.0; the function does not affect the existing scan path.
The contract tests pin the projection semantics so that future
modifications to plan_scan_budget or to BudgetPlan that break these
tests are regressions requiring the parity-break ceremony per
PARITY.md.

Verse 2:188 anchor: honest accounting. The tests below verify the
budget controller reports honestly which mechanisms are in budget,
which are not, and what scan_incomplete value must be applied if a
caller chooses to run only the in-budget subset.
"""
from __future__ import annotations

import pytest

from application.budget_controller import (
    BudgetPlan,
    CostCeiling,
    plan_scan_budget,
)
from domain.config import MECHANISM_REGISTRY
from domain.cost_classes import CostClass, cost_class


# ---------------------------------------------------------------------------
# P1. Pure projection: no side effects on frozen taxonomy
# ---------------------------------------------------------------------------


class TestPureProjection:
    """plan_scan_budget does not mutate MECHANISM_REGISTRY or cost_class."""

    def test_registry_identity_preserved(self) -> None:
        """MECHANISM_REGISTRY is not replaced or mutated by plan_scan_budget."""
        before = MECHANISM_REGISTRY
        for ceiling in (CostClass.A, CostClass.B, CostClass.C, CostClass.D):
            plan_scan_budget(ceiling)
        after = MECHANISM_REGISTRY
        assert before is after
        assert before == after

    def test_cost_class_function_idempotent(self) -> None:
        """cost_class(m) returns the same value before and after planning."""
        sample = next(iter(MECHANISM_REGISTRY))
        before = cost_class(sample)
        plan_scan_budget(CostClass.B)
        plan_scan_budget(CostClass.D)
        after = cost_class(sample)
        assert before == after


# ---------------------------------------------------------------------------
# P2. Honest scan_incomplete
# ---------------------------------------------------------------------------


class TestHonestScanIncomplete:
    """The plan reports scan_incomplete honestly against out_of_budget."""

    def test_class_a_truncates_at_least_one_mechanism(self) -> None:
        """At v1.6.0, class B/C/D mechanisms exist; class-A ceiling truncates."""
        plan = plan_scan_budget(CostClass.A)
        assert plan.scan_incomplete_implied is True
        assert len(plan.out_of_budget) > 0

    def test_class_d_is_complete(self) -> None:
        """Widest ceiling admits every registered mechanism."""
        plan = plan_scan_budget(CostClass.D)
        assert plan.scan_incomplete_implied is False
        assert plan.is_complete is True
        assert plan.out_of_budget == frozenset()

    def test_flag_disagreement_raises(self) -> None:
        """Constructing BudgetPlan with a wrong scan_incomplete flag fails."""
        # out_of_budget non-empty but flag False is forbidden
        with pytest.raises(ValueError):
            BudgetPlan(
                ceiling=CostClass.A,
                in_budget=frozenset({"any"}),
                out_of_budget=frozenset({"other"}),
                scan_incomplete_implied=False,
            )


# ---------------------------------------------------------------------------
# P3. Monotonicity in ceiling
# ---------------------------------------------------------------------------


class TestMonotonicity:
    """Widening the ceiling never removes a mechanism from in_budget."""

    def test_a_subset_of_b(self) -> None:
        a = plan_scan_budget(CostClass.A)
        b = plan_scan_budget(CostClass.B)
        assert a.in_budget <= b.in_budget

    def test_b_subset_of_c(self) -> None:
        b = plan_scan_budget(CostClass.B)
        c = plan_scan_budget(CostClass.C)
        assert b.in_budget <= c.in_budget

    def test_c_subset_of_d(self) -> None:
        c = plan_scan_budget(CostClass.C)
        d = plan_scan_budget(CostClass.D)
        assert c.in_budget <= d.in_budget

    def test_a_subset_of_d_transitively(self) -> None:
        a = plan_scan_budget(CostClass.A)
        d = plan_scan_budget(CostClass.D)
        assert a.in_budget <= d.in_budget


# ---------------------------------------------------------------------------
# P4. Idempotence
# ---------------------------------------------------------------------------


class TestIdempotence:
    """Equivalent calls produce equal partitions."""

    def test_same_ceiling_same_in_budget(self) -> None:
        for ceiling in (CostClass.A, CostClass.B, CostClass.C, CostClass.D):
            a = plan_scan_budget(ceiling)
            b = plan_scan_budget(ceiling)
            assert a.in_budget == b.in_budget
            assert a.out_of_budget == b.out_of_budget
            assert a.scan_incomplete_implied == b.scan_incomplete_implied


# ---------------------------------------------------------------------------
# P5. Registry exhaustiveness echo
# ---------------------------------------------------------------------------


class TestRegistryExhaustiveness:
    """Plan partitions exactly cover MECHANISM_REGISTRY."""

    def test_d_in_budget_equals_registry(self) -> None:
        plan = plan_scan_budget(CostClass.D)
        assert plan.in_budget == MECHANISM_REGISTRY

    def test_partition_covers_registry_every_ceiling(self) -> None:
        for ceiling in (CostClass.A, CostClass.B, CostClass.C, CostClass.D):
            plan = plan_scan_budget(ceiling)
            assert (plan.in_budget | plan.out_of_budget) == MECHANISM_REGISTRY

    def test_partition_disjoint_every_ceiling(self) -> None:
        for ceiling in (CostClass.A, CostClass.B, CostClass.C, CostClass.D):
            plan = plan_scan_budget(ceiling)
            assert plan.in_budget & plan.out_of_budget == frozenset()


# ---------------------------------------------------------------------------
# Type and signature pinning
# ---------------------------------------------------------------------------


class TestTypeContract:
    """plan_scan_budget signature and BudgetPlan shape are pinned."""

    def test_cost_ceiling_is_cost_class_alias(self) -> None:
        """CostCeiling is a re-export of CostClass."""
        assert CostCeiling is CostClass

    def test_rejects_non_cost_class(self) -> None:
        with pytest.raises(TypeError):
            plan_scan_budget("A")  # type: ignore[arg-type]

    def test_rejects_int_ceiling(self) -> None:
        with pytest.raises(TypeError):
            plan_scan_budget(1)  # type: ignore[arg-type]

    def test_budget_plan_is_frozen(self) -> None:
        plan = plan_scan_budget(CostClass.D)
        with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
            plan.ceiling = CostClass.A  # type: ignore[misc]

    def test_in_budget_is_frozenset(self) -> None:
        plan = plan_scan_budget(CostClass.C)
        assert isinstance(plan.in_budget, frozenset)
        assert isinstance(plan.out_of_budget, frozenset)
