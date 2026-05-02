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

**The parity invariant is conditional on the correctness of the reference implementation.** When a v0 finding, score, error message, or output shape is demonstrated to be incorrect — by an external corpus, a security advisory, an end-user report, or an internal review — the parity baseline is updated.

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

## Maintainer

Bilal Syed Arfeen, project lead.
