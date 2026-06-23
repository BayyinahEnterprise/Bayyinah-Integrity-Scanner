"""
v1.6.0 (Round 16) Q-PRO-3 honest budget controller.

Verse 2:188 anchor:
    وَلَا تَأْكُلُوا أَمْوَالَكُم بَيْنَكُم بِالْبَاطِلِ
    "And do not consume one another's wealth unjustly."

The architectural reading: when a caller imposes a cost-class budget on
the scan, the result must report honestly which mechanisms ran and which
were skipped, and the scan_incomplete signal must flow to
apply_scan_incomplete_clamp so the score reflects truncation rather than
hiding it.

This module ships at v1.6.0 as a PURE PROJECTION layer:

  - The functions in this module compute budget plans against the
    frozen MECHANISM_REGISTRY and MECHANISM_COST_CLASS taxonomy.
  - Nothing in this module mutates ScanService.scan() signature
    behavior. The scan call path is unchanged at v1.6.0.
  - Downstream consumers (CLI batch runners, API hot path projections,
    cost dashboards) can call plan_scan_budget() to know which
    mechanisms a given cost ceiling would dispatch BEFORE invoking
    a scan.

Wiring plan_scan_budget into ScanService.scan() as a runtime gate is
deferred to a later release with explicit PARITY ceremony per
PARITY.md (current scan signature is parity-pinned against
bayyinah_v0_1.scan_pdf on every Phase 0 fixture, so a new parameter
must go through the five-step parity-break procedure).

Cost-class taxonomy reference: domain/cost_classes.py
  Class A: structural address, O(1) per address
  Class B: indexed content walk, O(content) shared
  Class C: cross-correlation, O(n^2) bounded
  Class D: full re-parse, O(file_size)

Honest properties pinned by tests in
tests/contracts/test_budget_controller.py:

  P1. Pure projection: plan_scan_budget(C) returns the subset of
      MECHANISM_REGISTRY whose cost_class is <= C, with no side
      effects on the frozen taxonomy.
  P2. Honest scan_incomplete: if any registered mechanism is OUT of
      budget for ceiling C, BudgetPlan(C).scan_incomplete_implied is
      True. This is the contract that downstream consumers of the
      plan must respect when feeding scan_incomplete to
      apply_scan_incomplete_clamp.
  P3. Monotonicity: plan_scan_budget(A).in_budget is a subset of
      plan_scan_budget(B).in_budget is a subset of
      plan_scan_budget(C).in_budget is a subset of
      plan_scan_budget(D).in_budget == MECHANISM_REGISTRY.
  P4. Idempotence: plan_scan_budget(C) called twice with the same
      ceiling returns plans whose in_budget / out_of_budget sets
      are equal.
  P5. Registry exhaustiveness echo: plan_scan_budget(D).in_budget
      equals MECHANISM_REGISTRY exactly. The widest budget admits
      every registered mechanism.

Scope boundary (per CODING_STRATEGY §6 v1.6.0 + Cow Episode
discipline):

  IN scope at v1.6.0:
    - plan_scan_budget(ceiling) pure function
    - BudgetPlan dataclass surfacing in_budget / out_of_budget /
      scan_incomplete_implied
    - CostCeiling enum aliasing CostClass (re-export for explicit
      "this is a budget request" call site)
    - Contract pin tests in tests/contracts/test_budget_controller.py

  OUT of scope at v1.6.0 (deferred to later rounds):
    - ScanService.scan() signature change (parity-break ceremony)
    - Wall-clock or memory budget (handled by v1.2.1 subprocess
      isolation per Q6 closure)
    - Supply-chain budget (out of scope per Q-PRO-4 disposition in
      docs/supply_chain_disposition.md)
    - Per-format budget (cost taxonomy is per-mechanism, not per-format;
      cross-format budget composition deferred to v3.0+ per
      ROADMAP_TO_V5.md)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet

from domain.cost_classes import (
    CostClass,
    MECHANISM_COST_CLASS,
    cost_class,
)
from domain.config import MECHANISM_REGISTRY


# ---------------------------------------------------------------------------
# CostCeiling alias
# ---------------------------------------------------------------------------
# CostCeiling is a re-export of CostClass under a name that documents intent
# at the call site. A function signature reading
#     plan_scan_budget(ceiling: CostCeiling)
# is more honest than
#     plan_scan_budget(ceiling: CostClass)
# because the parameter is a budget request, not a classification of the
# parameter itself. The two are the same enum at runtime.

CostCeiling = CostClass


# ---------------------------------------------------------------------------
# Cost-class ordering
# ---------------------------------------------------------------------------
# The cost taxonomy A < B < C < D is not implicit in the Enum value strings.
# It is named here explicitly so the comparison "mechanism m is in budget
# for ceiling C" is auditable.

_COST_ORDER: dict[CostClass, int] = {
    CostClass.A: 1,
    CostClass.B: 2,
    CostClass.C: 3,
    CostClass.D: 4,
}


def _le_class(mech_class: CostClass, ceiling: CostClass) -> bool:
    """Return True iff mech_class is at or below ceiling in cost-order.

    A <= A, A <= B, A <= C, A <= D
    B <= B, B <= C, B <= D
    C <= C, C <= D
    D <= D

    All other comparisons return False.
    """
    return _COST_ORDER[mech_class] <= _COST_ORDER[ceiling]


# ---------------------------------------------------------------------------
# BudgetPlan dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BudgetPlan:
    """A read-only plan describing which mechanisms a budget admits.

    Fields:
        ceiling: the CostCeiling the plan was computed for.
        in_budget: frozenset of mechanism names whose cost class is
                   at or below the ceiling.
        out_of_budget: frozenset of mechanism names whose cost class is
                       above the ceiling. Disjoint from in_budget.
        scan_incomplete_implied: True iff out_of_budget is non-empty.
                                 This is the value a downstream caller
                                 must pass to apply_scan_incomplete_clamp
                                 if they choose to run only in_budget
                                 mechanisms.

    Invariants (asserted in __post_init__):
        - in_budget union out_of_budget == MECHANISM_REGISTRY
        - in_budget intersection out_of_budget == empty
        - scan_incomplete_implied == (len(out_of_budget) > 0)
    """

    ceiling: CostCeiling
    in_budget: FrozenSet[str]
    out_of_budget: FrozenSet[str]
    scan_incomplete_implied: bool

    def __post_init__(self) -> None:
        union = self.in_budget | self.out_of_budget
        if union != MECHANISM_REGISTRY:
            missing = MECHANISM_REGISTRY - union
            extra = union - MECHANISM_REGISTRY
            raise ValueError(
                "BudgetPlan partition does not cover MECHANISM_REGISTRY: "
                f"missing={sorted(missing)[:5]} extra={sorted(extra)[:5]}"
            )
        if self.in_budget & self.out_of_budget:
            overlap = sorted(self.in_budget & self.out_of_budget)[:5]
            raise ValueError(
                f"BudgetPlan in_budget and out_of_budget overlap: {overlap}"
            )
        expected_incomplete = len(self.out_of_budget) > 0
        if self.scan_incomplete_implied != expected_incomplete:
            raise ValueError(
                "BudgetPlan.scan_incomplete_implied disagrees with "
                f"out_of_budget cardinality: flag={self.scan_incomplete_implied} "
                f"out_of_budget_count={len(self.out_of_budget)}"
            )

    @property
    def is_complete(self) -> bool:
        """True iff every registered mechanism is in budget."""
        return not self.scan_incomplete_implied


# ---------------------------------------------------------------------------
# plan_scan_budget
# ---------------------------------------------------------------------------


def plan_scan_budget(ceiling: CostCeiling) -> BudgetPlan:
    """Compute the budget plan for the given cost ceiling.

    Args:
        ceiling: a CostCeiling (alias of CostClass) naming the highest
                 cost class the caller is willing to admit.

    Returns:
        A BudgetPlan partitioning MECHANISM_REGISTRY into in_budget and
        out_of_budget against the ceiling.

    Raises:
        TypeError: if ceiling is not a CostCeiling / CostClass.

    Pure: no side effects on MECHANISM_REGISTRY, MECHANISM_COST_CLASS,
    or any other module-level state. Safe to call repeatedly with the
    same argument; equivalent calls return equal plans.
    """
    if not isinstance(ceiling, CostClass):
        raise TypeError(
            f"plan_scan_budget() ceiling must be a CostCeiling (CostClass); "
            f"got {type(ceiling).__name__}"
        )

    in_budget: set[str] = set()
    out_of_budget: set[str] = set()
    for mech in MECHANISM_REGISTRY:
        mech_class = cost_class(mech)
        if _le_class(mech_class, ceiling):
            in_budget.add(mech)
        else:
            out_of_budget.add(mech)

    return BudgetPlan(
        ceiling=ceiling,
        in_budget=frozenset(in_budget),
        out_of_budget=frozenset(out_of_budget),
        scan_incomplete_implied=(len(out_of_budget) > 0),
    )


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------

__all__ = [
    "BudgetPlan",
    "CostCeiling",
    "plan_scan_budget",
]
