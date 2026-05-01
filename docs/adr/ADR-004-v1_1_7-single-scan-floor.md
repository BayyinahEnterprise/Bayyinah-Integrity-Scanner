# ADR-004 - Single-scan latency treated as the floor; future performance work targets throughput (v1.1.7)

- Status: accepted
- Date: 2026-04-30
- Deciders: Bilal Syed Arfeen (project lead)
- Supersedes: nothing
- Superseded by: nothing

## Context

v1.1.7 migrated four of the six `BatinObjectAnalyzer` sub-mechanisms to
read from the per-scan ContentIndex (`_scan_incremental_updates`,
`_scan_metadata`, `_scan_embedded_files`, `_scan_tounicode_cmaps`).
The v1.1.7 prompt predicted a 10 to 20 percent additional reduction in
single-scan P50 on dense PDFs on top of v1.1.4's 32 percent. The
measurement on the four-density panel was within noise of v1.1.6:

| Fixture | v1.1.6 P50 | v1.1.7 P50 |
|---|---:|---:|
| white_paper_19p | 206 ms | 205 ms |
| clean_50p_native | 134 ms | 135 ms |
| safety_report_220p | 13850 ms | 13858 ms |

The structural migration shipped on its own merits (reduced coupling
between four mechanisms and the pypdf reader, ContentIndex extended
with `fonts_by_page` and `catalog["embedded_files"]`). The headline
P50 did not move because the two unmigrated walks (`_scan_catalog`,
`_scan_annotations`) still drive the dominant cost: the pypdf
document parse plus the per-page `/Annots` walk via pypdf. Those
two walks emit `concealed=self._safe_str(obj)[:N]` whose pypdf
`IndirectObject(idnum, gen, <id>)` repr is byte-parity-critical.
pikepdf produces a different repr shape, so a direct migration to
read from ContentIndex would change finding text and break the v0.1
parity test sweep.

This ADR records the decision on which forward path to take.

## Decision

The project treats v1.1.7's measured single-scan P50 as the practical
floor for the v1.x line and shifts future performance work to
throughput rather than per-scan latency.

Specifically:

1. No further single-scan ContentIndex migrations are planned for the
   v1.x line.
2. Future v1.x performance work, if any, targets throughput axes:
   parallel scans, batch endpoints, registry-level caching across
   files in the same scan session, streaming partial findings.
3. Single-scan latency reduction below the v1.1.7 floor is reopened
   only at the v2.0 boundary and only as part of a pypdf removal.

## Rejected alternatives

### Option A: Remove pypdf, migrate everything to pikepdf (v2.0)

Replace every `pypdf` read with the `pikepdf` equivalent. Re-baseline
the v0.1 parity tests against the new `concealed` repr shape. Largest
expected perf upside (the per-page `/Annots` walk via pikepdf is
materially faster than via pypdf on dense PDFs), largest test churn.

Rejected for the v1.x line because:

- The v0-to-v0.1 parity invariant is a load-bearing trust artifact for
  the white paper, the README, and the public corpus disclosure. Every
  release from 0.2.x through 1.1.7 has held it. Breaking it requires a
  major version bump and a separate parity story for v2.0.
- The 56-day arc to the June 9 2026 competition does not have time
  for a 2.0 cut.
- The 14-second P50 on the 220-page native-text dense report is
  already within range for compliance-grade institutional use. Further
  per-scan reduction is a quality-of-implementation improvement, not
  a market-differentiating one.

Reopened as a candidate at the v2.0 boundary, not before.

### Option B: Repr-shim in v1.2.x

Extend ContentIndex preflight to capture pypdf-shaped
`IndirectObject(idnum, gen, <id>)` repr strings at index-build time
(open both pikepdf and a pypdf reader during preflight, walk pypdf
specifically for the `concealed` payloads, store them keyed by
catalog path). Then migrate `_scan_catalog` and `_scan_annotations`
to read those captured strings from ContentIndex.

Rejected for now because:

- The double-walk (pikepdf for the index plus pypdf for the
  repr-shim) erases most of the single-scan saving the migration
  would buy. The pypdf parse is the dominant cost and would still
  fire once per scan.
- It buys back perhaps a few percent on dense PDFs at the cost of a
  meaningful increase in ContentIndex preflight surface area and a
  new failure mode (pikepdf-side index disagrees with pypdf-side
  repr-shim).
- It is a strict subset of Option A on engineering value: it pays
  for the parity-shim engineering twice if Option A eventually
  ships.

Reopened only if a customer or judge specifically asks for a
v1.x release that closes those two walks without a major version
bump.

## Consequences

### Positive

- The CHANGELOG and ADR record a measured null result with a named
  root cause. The Munafiq Protocol values this kind of disclosure;
  shipping it is consistent with the public miss-list discipline.
- Future performance discussions are anchored to throughput axes,
  which are the axes a compliance-grade institutional buyer cares
  about ("can you scan our document corpus" rather than "how fast
  is one scan").
- The v1.1.7 ContentIndex extensions (`fonts_by_page`,
  `catalog["embedded_files"]`, `FontToUnicodeInfo`) remain
  available for any future detector that needs them, regardless of
  which option is eventually taken.

### Negative

- The "10 to 20 percent additional reduction" wording in the v1.1.7
  prompt did not deliver. The CHANGELOG documents this honestly.
- A judge or reviewer specifically benchmarking single-scan P50
  against another v1.x release will see flat numbers and may infer
  the project is out of single-scan ideas. The mitigation is the
  CHANGELOG paragraph and this ADR: the project is not out of
  ideas, it has chosen not to spend them on this axis in v1.x.

### Neutral

- The v1.1.7 structural migration stands as documented. No code
  is reverted. Future detectors that read from `fonts_by_page` or
  `catalog["embedded_files"]` get the index-first read path for
  free.

## Reopening criteria

This ADR is revisited if any of the following happens:

1. A customer or judge asks for a v1.x release with closed
   `_scan_catalog` / `_scan_annotations` migrations. Option B is then
   evaluated against the cost of building the repr-shim.
2. The v2.0 cut is scheduled. Option A is then the default plan and
   this ADR is superseded.
3. A throughput axis (parallel scans, batch endpoints) hits a wall
   that is solvable only by reducing single-scan latency. Then either
   Option A or Option B is reconsidered against the specific
   throughput bottleneck.

## References

- v1.1.7 CHANGELOG entry, "Not migrated (deferred)" section
- `docs/benchmarks/v1_1_4_four_density.py`
- `tests/analyzers/test_object_analyzer.py::test_parity_with_v0_1_object_layer_analyzer`
  (the parity invariant this ADR is in service of)
- ADR-002 (v1.1.5 spatial index) and ADR-003 (v1.1.6 registry
  short-circuit), which framed the cost-class taxonomy this ADR
  inherits
