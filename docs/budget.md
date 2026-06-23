# Budget controller contract (v1.6.0)

Canonical contract document for `application.budget_controller`, the
honest budget projection layer introduced at v1.6.0 (Round 16) per
`CODING_STRATEGY_v1_2_4_to_v2_0.md` §6 v1.6.0 Fatiha session.

Verse anchor: al-Baqarah 2:188 ("And do not consume one another's wealth
unjustly"). The architectural reading is honest accounting. A budget
controller that silently skips work without telling the caller is the
software analogue of consuming wealth unjustly: the caller asked for a
scan, the runtime ran less than a scan, and the report did not say so.

## §1 Surface

The v1.6.0 budget controller exports three public names:

- `BudgetPlan` -- a frozen dataclass describing the partition of
  `MECHANISM_REGISTRY` against a cost ceiling.
- `CostCeiling` -- an alias of `domain.cost_classes.CostClass` carrying
  the "this is a budget request" semantic at the call site.
- `plan_scan_budget(ceiling)` -- a pure function returning a
  `BudgetPlan` for the given ceiling.

Nothing else is part of the public surface. Modifications to other
names in the module that downstream consumers come to depend on are
the consumer's risk.

## §2 Properties

The properties below are pinned by
`tests/contracts/test_budget_controller.py`. Modifications that break
any of them require the parity-break ceremony per `PARITY.md`.

### §2.1 P1. Pure projection

`plan_scan_budget(C)` does not mutate `MECHANISM_REGISTRY`,
`MECHANISM_COST_CLASS`, or any module-level state. The frozen
authoritative taxonomy lives at `domain/cost_classes.py` and is the
input to the projection, never the output.

### §2.2 P2. Honest scan_incomplete

If any mechanism registered in `MECHANISM_REGISTRY` has a cost class
above the ceiling `C`, then `plan_scan_budget(C).scan_incomplete_implied`
is `True`.

A downstream caller that chooses to run only the `in_budget` subset
must pass this value to `apply_scan_incomplete_clamp` per `docs/score.md`
§2.1. The clamp pin (`SCAN_INCOMPLETE_CLAMP = 0.5`) ensures the integrity
score reflects truncation rather than reporting a clean scan over a
truncated pipeline.

### §2.3 P3. Monotonicity in ceiling

For any two ceilings C1 and C2 with C1 below C2 in the cost order
(A < B < C < D):

    plan_scan_budget(C1).in_budget is a subset of plan_scan_budget(C2).in_budget

Widening the ceiling never removes a mechanism from in_budget.

### §2.4 P4. Idempotence

`plan_scan_budget(C)` called twice with the same ceiling returns plans
whose `in_budget` / `out_of_budget` / `scan_incomplete_implied` fields
are equal.

### §2.5 P5. Registry exhaustiveness

For every ceiling C, `plan.in_budget` and `plan.out_of_budget` together
exactly cover `MECHANISM_REGISTRY` and are disjoint. The widest ceiling
`CostClass.D` admits every registered mechanism:

    plan_scan_budget(CostClass.D).in_budget == MECHANISM_REGISTRY

## §3 What this layer does NOT do

The v1.6.0 budget controller is a pure projection. It does NOT:

1. Modify `ScanService.scan()` signature or call path. The existing
   `mode: str = "forensic"` parameter and the production / forensic mode
   semantics remain exactly as documented in `application/scan_service.py`.
   A future release MAY wire the budget controller into the scan call
   path via the five-step parity-break procedure per `PARITY.md`.
2. Enforce a wall-clock or memory budget. Subprocess timeout isolation
   is handled by the v1.2.1 Q6 closure (30-second wall-clock cap +
   subprocess isolation).
3. Compose budgets across files in a batch scan. Per-batch budget
   accounting is deferred to v3.0+ enterprise tier per
   `ROADMAP_TO_V5.md`.
4. Implement a supply-chain budget (SBOM cost, in-toto attestation
   verification cost). Supply-chain detection itself is out of scope
   per `docs/supply_chain_disposition.md` (Q-PRO-4 closure).
5. Add new cost classes. The taxonomy at `domain/cost_classes.py` is
   frozen at A, B, C, D and is the authoritative source.

## §4 Migration notes for downstream consumers

The v1.6.0 release adds the budget controller WITHOUT changing the
existing scan call surface. Consumers continue to call
`ScanService.scan(file_path, mode="forensic")` exactly as before; no
behavior changes.

Consumers that wish to compute a budget plan ahead of scan dispatch
import the controller directly:

    from application.budget_controller import plan_scan_budget, CostCeiling

    plan = plan_scan_budget(CostCeiling.B)
    if plan.scan_incomplete_implied:
        # caller's choice: scan anyway and clamp the score, or refuse
        # to scan and report the budget as infeasible.
        ...

There is no implicit wiring; the consumer remains responsible for
deciding what to do with the plan.

## §5 Cross-references

- `application/budget_controller.py` -- implementation source.
- `tests/contracts/test_budget_controller.py` -- contract pin tests.
- `domain/cost_classes.py` -- authoritative cost-class taxonomy.
- `domain/config.py` -- `MECHANISM_REGISTRY` frozen set.
- `domain/value_objects.py` -- `apply_scan_incomplete_clamp`.
- `docs/score.md` -- score-function contract (clamp truth table).
- `docs/supply_chain_disposition.md` -- Q-PRO-4 scope disposition.
- `QUESTIONS.md` Q-PRO-3 -- closure log entry citing this document.
- `CODING_STRATEGY_v1_2_4_to_v2_0.md` §6 v1.6.0 -- release plan.
- `PARITY.md` -- parity-break ceremony required for any modification
  that breaks the properties pinned above.
