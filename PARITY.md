# Parity Policy

Bayyinah ships `bayyinah_v0.py` and `bayyinah_v0_1.py` as reference implementations. The integration test suite asserts byte-identical PDF output between the modular implementation and these references on every Phase 0 fixture, and the invariant has held across every release from v0.2.x through v1.1.9.

This document defines the conditions under which the parity invariant may be broken and the procedure for breaking it.

## The invariant

`bayyinah.scan_pdf(path).to_dict() == bayyinah_v0.scan_pdf(path).to_dict()` for every fixture in the Phase 0 fixture corpus.

This is asserted by `tests/test_fixtures.py::test_v0_v01_parity` and re-verified after every phase.

## Why parity is the default

Reproducing the reference implementation byte-for-byte is the strongest possible structural guarantee of "we never silently changed behavior." A consumer pinning to a Bayyinah version can rely on the fact that the same input produces the same output bit-for-bit across the modular refactor. This is the substrate the Munafiq Protocol's additive-only discipline operates on.

## The trap

A guarantee that always reproduces v0 is also a guarantee that ships every defect in v0 forever. If v0 mis-classifies a finding, mis-rounds a score, or emits a key in the wrong order, parity locks that defect in. The parity invariant becomes a baseline that owns the codebase rather than a discipline the codebase chose.

## The conditional invariant

**The parity invariant is conditional on the correctness of the reference implementation.** When a v0 finding, score, error message, or output shape is demonstrated to be incorrect -- by an external corpus, a security advisory, an end-user report, or an internal review -- the parity baseline is updated.

The procedure:

1. Open an issue tagged `parity-break` with the demonstration of v0's defect.
2. Cross-reference the issue from `CHANGELOG.md` under a `Parity-break` heading for the release that contains the fix.
3. Update the affected fixture(s) in the Phase 0 corpus with both the old (defective) v0 output and the new (corrected) expected output, retaining the old as a regression artifact.
4. Update `tests/test_fixtures.py::test_v0_v01_parity` to assert the new expected output.
5. Bump the minor version. A parity break is, by definition, a behavior change, even when the new behavior is more correct than the old.

## What a parity break is not

A parity break is not a license to drift. The default remains identical-output. A parity break is a deliberate, reviewed, version-bumped, CHANGELOG-documented decision, not a side effect of refactoring. If a refactor changes output without a parity-break entry in the CHANGELOG, it is a regression and is treated as one.

## What a parity break is

A parity break is the discipline that lets the codebase honor the structural-honesty thesis recursively: the project's own claim that "we never silently change behavior" is conditional on the project never silently failing to fix things. The conditional invariant is what makes the parity claim load-bearing instead of a trap.

## Parity-break ledger

The parity-break ceremony per the procedure above records each invariant
modification with rationale, scope, and downstream-consumer migration
notes. Per FRAMEWORK.md, parity breaks are reviewed, version-bumped, and
publicly declared events; this ledger is the canonical record.

### v1.3.0 (Round 13) -- tounicode_anomaly tier reclassification 1 -> 2

**Date:** 2026-06-22.
**Driving cycle:** Round 13 audit-of-self per RETIREMENT_LEDGER.md;
deferred from v1.2.4 Round 12 calibration corrective with the proper
PARITY.md procedure (issue tag, fixture update, test update, minor bump,
CHANGELOG Parity-break heading).
**Mechanism:** `tounicode_anomaly`.
**Locus:** `domain/config.py` TIER table.
**Old (v0/v0_1 reference) tier:** 1.
**New (v1.3.0+ modular) tier:** 2.
**Rationale:** v1.2.4's Round 12 corrective established that legitimate
TeX-stack ToUnicode CMaps (OT1/T1 fonts with Greek/math glyph targets at
unusual slots, ZWNJ at slot 0x17, etc.) produce ToUnicode shape that the
heuristic legitimately classifies as anomalous, even when no concealment
is present. The pdfTeX hyperref/GoTo and LibreOffice destination-array
calibration corrections shipped at v1.2.4 reduced the false-positive
rate but did not eliminate the structural-pattern-vs-intent ambiguity.
Tier 1 implies high-confidence concealment; tier 2 implies structural
pattern with intent-ambiguity. Tier 2 is the substrate-honest
classification for tounicode_anomaly given the Round 12 calibration
evidence.
**Affected fixtures:** any Phase 0 fixture exercising tounicode_anomaly
emission; explicitly `tests/fixtures/_fonts/tounicode_cmap.pdf` and any
PDF fixture with a non-canonical ToUnicode CMap. The pre-v1.3.0
expected output had tier=1; post-v1.3.0 emits tier=2. Old expected
output retained as the v0/v0_1 reference baseline; new expected output
is the v1.3.0+ canonical.
**Test update:** `tests/test_integration.py::test_scan_pdf_parity_with_v0`
and `test_scan_pdf_parity_with_v01` apply a documented v1.3.0
parity-break remapper to the v0/v0_1 theirs_tuples list, coercing
tounicode_anomaly findings' tier from 1 to 2 before equality comparison.
The remapper is named `_v1_3_0_tounicode_tier_remap` and is documented
in test_integration.py with cross-reference to this ledger entry.
**Migration note for downstream consumers:** consumers pinned to
v1.2.x tounicode_anomaly tier=1 must update to tier=2 at the v1.3.0
upgrade. Triage workflows that partition by tier route tounicode_anomaly
to the tier-2 (structural-pattern) workflow rather than tier-1
(high-confidence concealment) starting at v1.3.0. The mechanism's
detection logic is unchanged; only the tier classification of its
output changes.
**Version bump:** 1.2.4 -> 1.3.0 (minor, per PARITY.md procedure step
5: parity break is a behavior change even when the new behavior is
more correct than the old).
**Q2 closure data point #1:** this parity break is the first empirical
data point for QUESTIONS.md Q2 (Is the parity-with-v0 invariant
load-bearing or contingent?). The discipline answer materializes as:
the invariant is contingent on v0 correctness; the ceremony exists
precisely for this case. Q2 accumulates evidence across subsequent
parity breaks; v1.3.0 is data point 1.

## Maintainer

Bilal Syed Arfeen, project lead.
