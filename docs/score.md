# Bayyinah Score Function Contract

**Version:** v1.4.0 pinned.
**Authority:** Q3 + Q4 closure (per QUESTIONS.md and CODING_STRATEGY §6 v1.4.0).
**Verse anchor:** al-Baqarah 2:286 -- "Allah does not charge a soul except [with that within] its capacity."
**Status:** PINNED. Future modifications require the parity-break ceremony per PARITY.md.

This document is the canonical contract for `compute_muwazana_score`, `apply_scan_incomplete_clamp`, and `tamyiz_verdict`. It documents EXISTING behavior as it ships at v1.4.0; it does NOT redesign. Future modifications to score or clamp behavior require an explicit parity-break ceremony per PARITY.md procedure with calibration evidence.

## 1. `compute_muwazana_score` shape

**Locus:** `domain/value_objects.py::compute_muwazana_score`.

**Signature:** `compute_muwazana_score(findings: Iterable[Finding]) -> float`.

**Semantics:**

```
score = clamp(1.0 - sum(severity * confidence for f in findings), 0.0, 1.0)
```

**Purity:** pure, idempotent, no side effects. Each finding's contribution depends only on its `severity` and `confidence` fields.

### 1.1 Boundary conditions (pinned)

| Input | Output |
|---|---|
| empty `findings` iterable | `1.0` (no deductions) |
| `findings = [Finding(severity=0.0, confidence=0.0, ...)]` | `1.0` (zero deduction) |
| `findings = [Finding(severity=1.0, confidence=1.0, ...)]` | `0.0` (one finding saturates lower bound) |
| `findings = [Finding(severity=0.5, confidence=1.0, ...)]` | `0.5` (single half-severity finding) |
| sum of `severity*confidence` > 1.0 | `0.0` (lower clamp) |
| sum of `severity*confidence` < 0.0 (theoretical; should not occur in practice) | `0.0` (the function clamps at 0; the >1.0 branch maps to 1.0; mathematically the input domain ensures non-negative summation) |

### 1.2 Monotonicity (pinned)

For any two iterables `f1` and `f2` where `f2 = f1 + [Finding(severity=s, confidence=c, ...)]` with `s > 0` and `c > 0`:

```
compute_muwazana_score(f2) <= compute_muwazana_score(f1)
```

Adding a finding with positive severity-confidence product never increases the score. Equality holds when the post-addition sum still exceeds 1.0 (both already clamped to 0.0).

### 1.3 Order independence (pinned)

The score is invariant under permutation of the `findings` iterable. For any permutation `perm`:

```
compute_muwazana_score(findings) == compute_muwazana_score(perm(findings))
```

This follows from the commutativity of summation; pinned as a contract regression guard.

### 1.4 Rounding tolerance (pinned)

The function uses standard IEEE 754 double-precision floating-point arithmetic. No explicit rounding is applied within the function body. Consumers performing equality comparisons should allow `abs(score_a - score_b) < 1e-9` tolerance for cross-implementation byte-identity comparisons (per `_finding_tuple` convention in `tests/test_integration.py`).

### 1.5 Patent claim cross-reference

`compute_muwazana_score` shape is the operational substrate for Patent Claim 8 (per CODING_STRATEGY §7 patent invariant clause). Modifications escalate to counsel review BEFORE merge.

## 2. `apply_scan_incomplete_clamp` semantics

**Locus:** `domain/value_objects.py::apply_scan_incomplete_clamp`.

**Signature:** `apply_scan_incomplete_clamp(score: float, *, scan_incomplete: bool) -> float`.

**Constant:** `SCAN_INCOMPLETE_CLAMP = 0.5` (`domain/config.py:2884`).

**Semantics:**

```
if scan_incomplete and score > SCAN_INCOMPLETE_CLAMP:
    return SCAN_INCOMPLETE_CLAMP
return score
```

### 2.1 Truth table (pinned)

| `scan_incomplete` | input `score` | output `score` |
|---|---|---|
| `False` | any value in `[0.0, 1.0]` | input unchanged (pass-through) |
| `True` | `score <= 0.5` | input unchanged (already below clamp) |
| `True` | `score > 0.5` | `0.5` (clamped down) |
| `True` | `score == 0.5` | `0.5` (boundary preserves) |
| `True` | `score == 1.0` | `0.5` (clamped) |

### 2.2 Purity (pinned)

Pure function; no side effects; idempotent.

### 2.3 Composition with `compute_muwazana_score` (pinned)

The two functions are deliberately separate: `compute_muwazana_score` weighs the findings it has; `apply_scan_incomplete_clamp` reflects the meta-question of whether those findings constitute a complete picture. Callers apply the clamp post-score per the registry pattern (`analyzers/registry.py:494`).

### 2.4 Q4 closure note (pinned)

Q4 ("the `0.5` clamp lives inside a continuous distribution") is closed at v1.4.0 by this contract pinning. The clamp value `0.5` is the canonical scan-incomplete signal; consumers needing unambiguous disambiguation use the companion `scan_incomplete: bool` field on `IntegrityReport` rather than inferring from the score channel. The score channel's `0.5` value is intentionally overloaded; the bool field is the type-safe channel. Future redesigns proposing `score=None` for incomplete scans would require the parity-break ceremony.

## 3. `tamyiz_verdict` decision table

**Locus:** `domain/value_objects.py::tamyiz_verdict`.

**Signature:** `tamyiz_verdict(report: IntegrityReport) -> Verdict`.

The decision table is checked top-down; first match wins:

```
0. any Tier 0 (routing) finding present
       -> VERDICT_MUGHLAQ (routing in dispute)
1. scan_incomplete OR error present
       -> VERDICT_MUGHLAQ (closed / withheld)
2. score == 1.0 AND no findings
       -> VERDICT_SAHIH (sound)
3. score < 0.3 AND at least one tier-1 finding
       -> VERDICT_MUNAFIQ (severe, verified concealment)
4. score < 0.7
       -> VERDICT_MUKHFI (concealment detected)
5. otherwise (0.7 <= score < 1.0, or score == 1.0 with low-severity findings)
       -> VERDICT_MUSHTABIH (suspicious)
```

This table is pinned at v1.4.0. Modifications to rule order or thresholds (`0.3`, `0.7`) require parity-break ceremony.

### 3.1 Patent claim cross-reference

`tamyiz_verdict` decision logic implements the five-verdict structure of the verdict aggregator (component 150 per CODING_STRATEGY §7 patent invariant clause). Modifications escalate to counsel review BEFORE merge.

## 4. Q3 closure note

Q3 ("the score function collapses heterogeneous risk") is closed at v1.4.0 by this contract pinning the existing continuous-and-saturating shape. The decision is NOT to split into separate score-and-finding-count axes at this release. Rationale:

- The current shape is byte-identical to `bayyinah_v0.compute_integrity_score`; splitting would be a parity break with broad downstream impact.
- Consumers needing finding-count-resolution access the `findings` list directly on `IntegrityReport`.
- Consumers needing per-finding tier-resolution access `finding.tier` directly.
- The score channel is intentionally compressed; the report object provides full resolution.

Future redesigns proposing a split would require: (a) calibration evidence that triage workflows materially benefit from the split; (b) the parity-break ceremony per PARITY.md; (c) a migration shim for downstream consumers per v1.4.0 STRATEGY_TO_V2.md slip discipline pattern.

## 5. Regression coverage

This contract is regression-tested in:

- `tests/contracts/test_muwazana_score_shape.py` -- pins §1 boundary, monotonicity, order independence, rounding tolerance.
- `tests/contracts/test_scan_incomplete_clamp.py` -- pins §2 truth table, purity, idempotence.

Both files are added at v1.4.0 per CODING_STRATEGY §6 v1.4.0 Step 6 task (3). Any future modification to `compute_muwazana_score`, `apply_scan_incomplete_clamp`, or the `tamyiz_verdict` decision table that breaks these tests is a regression and must go through the parity-break ceremony per PARITY.md.

## 6. Closing

This contract is the substrate-honest pin of the score function shape at v1.4.0. It documents WHAT the function currently does; it does NOT redesign. Per CODING_STRATEGY §6 v1.4.0 Cow Episode anchor: the contract is pinned against the EXISTING fixture set; expanded coverage in subsequent rounds is driven only by empirical need.

> Rabbana taqabbal minna. Innaka anta as-Sami'ul 'Alim.

La hawla wa la quwwata illa billah.
