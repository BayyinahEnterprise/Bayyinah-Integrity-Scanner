# ADR-003 - Registry-level cost-class-ordered short-circuit (v1.1.6)

- Status: accepted
- Date: 2026-04-30
- Deciders: Bilal Syed Arfeen (project lead)
- Supersedes: nothing
- Superseded by: nothing

## Context

v1.1.4 introduced cost classes (A, B, C, D) per detector mechanism in
`domain/cost_classes.py` and an opt-in production mode that returned
early on Tier 1, confidence>=0.9 findings *within* a single analyzer
(the PDF analyzer). The cross-analyzer dispatch order was still the
registration order, so a class-D analyzer registered before any class-A
analyzer would still run first in production mode and waste latency
that an early-firing class-A finding would have made redundant.

v1.1.5 deferred the cross-analyzer ordering to v1.1.6.

The four items the v1.1.4 CHANGELOG named under "Deferred to v1.1.5"
collapsed to one for v1.1.6: pass-by-pass cost-class-ordered early
termination at the registry level. The `BatinObjectAnalyzer` migration
to the content index and the F2 calibration plan keep their original
slots (v1.1.7 / v1.2 respectively).

## Decision

In `analyzers/registry.py`:

1. Each registered analyzer class has a primary cost class derived
   from the MAX of cost classes of every mechanism string it (or any
   one-hop sibling helper it imports from `analyzers.*`) emits. The
   resolution is via AST walk, cached with `lru_cache`. Analyzers may
   declare `primary_cost_class: ClassVar[CostClass]` to override the
   AST-derived value (used by test analyzers and for analyzers whose
   source module cannot be reliably introspected).

2. `AnalyzerRegistry._sorted_for_production()` returns the registered
   classes ordered by primary cost class (A, B, C, D), with stable
   within-class registration order.

3. `AnalyzerRegistry.scan_all(file_path, kind=..., mode="forensic"
   | "production")` adds a `mode` parameter:
   - `"forensic"` (default): registration-order dispatch, every
     applicable analyzer runs, byte-parity with v1.1.5 preserved.
   - `"production"`: cost-class-ordered dispatch, the loop exits the
     first time the merged report contains any Tier 1 finding at
     confidence >= 0.9.

4. `ScanService._scan_inner` threads `mode` through to every
   `self.registry.scan_all(...)` call so the live API path
   (`POST /scan?mode=production`) gets the registry-level
   short-circuit, not just the in-PDF-analyzer one.

5. The merged report shape is unchanged across modes. There is no new
   field for "terminated_early"; an observer can detect early
   termination only by counting findings or by counting analyzer
   invocations. Forensic-mode callers see no difference.

## Consequences

### Positive

- Adversarial files with a Tier-1, high-confidence finding skip every
  later cost-class B/C/D analyzer. Measured: 20 percent P50 reduction
  on `tests/fixtures/positive_combined.pdf` (16 findings forensic / 8
  findings production, 11.16 ms forensic / 8.98 ms production). See
  `docs/benchmarks/v1_1_6_production_mode.md`.
- Single-mechanism adversarial fixtures get small gains in the
  3 to 6 percent range (sub-millisecond) because dispatch order
  matters less when only one analyzer fires.
- Clean files run the same set of analyzers in both modes (no Tier-1
  finding ever fires, so the short-circuit predicate is never
  satisfied). Measured: P50 within stdev for both `clean.pdf`
  and `clean_50pg.pdf`.
- Determinism: production-mode dispatch order is fully determined
  by the registration order plus the cost-class taxonomy. The same
  registry on the same input produces the same analyzer sequence
  on every run.

### Negative

- The AST walk parses every analyzer module on first dispatch (per
  process). The result is cached by `lru_cache(maxsize=None)`. Cold-
  start cost is small (low milliseconds) but is real and is paid by
  the first scan after process start.
- An analyzer that genuinely has no mechanism literals in its source
  (none in the v1.1.6 registry, but possible in the future) falls
  through to `CostClass.D`. This is intentional and pessimistic: a
  silently unmapped analyzer runs LAST in production mode, never
  first; the
  `test_every_registered_analyzer_resolves_to_a_cost_class` test
  catches the case before it ships.

### Neutral

- The Tier 1 verdict is preserved across modes for every fixture
  in the corpus that produces a Tier 1 finding (pinned by
  `tests/test_registry_production_mode.py::test_production_mode_preserves_tier_1_verdict`).
  Production mode may surface fewer non-Tier-1 mechanisms; that is
  the explicit intent.

## Alternatives considered

### A. Per-analyzer mode switch instead of registry-level dispatch

Each analyzer would expose its own `production_mode` parameter and
the registry would call it unchanged. Rejected because the early
termination signal is global (any Tier-1 finding from any analyzer
short-circuits the rest of the pipeline) and a per-analyzer flag
would not let one analyzer's verdict skip a sibling analyzer.

### B. Replace registration order entirely with cost-class order

Forensic mode would also dispatch in cost-class order. Rejected
because the v1.1.5 test corpus has detector-level assertions that
depend on registration-order merge semantics, and cycling the order
without a forensic-mode opt-out would break parity with reference
implementations `bayyinah_v0.py` and `bayyinah_v0_1.py`.

### C. Surface "terminated_early" on the merged report

A boolean field on `IntegrityReport` that production mode sets to
`True` when the loop exited before running every applicable
analyzer. Rejected for v1.1.6 because the report shape is part of
the public Phase-0 contract and adding a field is a Phase-1
change. Reconsidered if a downstream consumer needs the signal.

## References

- `domain/cost_classes.py`: cost-class taxonomy, 155 mechanisms classified
  (55 A, 82 B, 8 C, 10 D).
- `analyzers/registry.py`: `_analyzer_primary_cost_class`,
  `_sorted_for_production`, `scan_all(mode=...)`.
- `application/scan_service.py`: `_scan_inner(mode=...)`.
- `tests/test_registry_production_mode.py`: 9 regression tests.
- `docs/benchmarks/v1_1_6_production_mode.py` and the accompanying
  Markdown report.
- ADR-002 (v1.1.5 spatial pre-filter) for the precedent of an
  optimization that preserves detection behaviour byte-for-byte.
