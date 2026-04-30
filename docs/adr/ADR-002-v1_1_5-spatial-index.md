# ADR-002, v1.1.5 spatial pre-filter for `overlapping_text`

**Status:** Accepted, 2026-04-30
**Author:** Bilal Syed Arfeen
**Reviewer:** Claude (Anthropic), Computer (Perplexity)
**Relates to:** v1.1.4 deferred items (CHANGELOG `### Deferred to v1.1.5`)

---

## Context

The `overlapping_text` mechanism in `analyzers/text_analyzer.py` ran an
all-pairs O(n^2) IoU comparison over every text span on every page.
On the v1.1.4 four-density panel, the dense 220-page native-text
report measured a P50 of 15,335 ms end-to-end, and a per-mechanism
profile attributed roughly 3,400 ms (about 22 percent of total) to
`_scan_overlapping_spans` alone. The 220-page document carries
~25,600 spans across all pages; sum-of-squares per page totals
~3.5 million IoU evaluations to surface zero findings.

The v1.1.4 CHANGELOG named "spatial indexing for `overlapping_text`
(R-tree) to fully collapse the dense-PDF class-C cost" as deferred to
v1.1.5. This ADR records the decision to ship that index without
adding a runtime dependency.

## Decision

Replace the O(n^2) inner loop with a stdlib uniform-grid candidate
generator (`_overlapping_pair_candidates` at module scope) that
emits only span-index pairs whose bounding boxes share at least one
grid cell. The IoU predicate (`_bbox_iou`) and the threshold
(`SPAN_OVERLAP_THRESHOLD = 0.5`) are unchanged, so any pair that
would have surfaced under the naive scan still surfaces.

### Why a uniform grid and not `rtree`

The wider scanner pinned its dependency block at four packages
(pymupdf, pypdf, pikepdf, mutagen) on purpose: every additional
parser the scanner pulls in is a parser an adversarial document can
target. `rtree` requires `libspatialindex` (a C library), which
broadens the install surface, complicates wheel availability across
the Python versions the CI matrix exercises, and adds a parser layer
that has no role in detection.

A uniform grid sized to the median span dimensions matches an
R-tree's asymptotic complexity on roughly uniformly sized boxes
(text spans on a page are exactly that case) and ships in pure
Python. This stays inside the scanner's existing architecture rule:
no new runtime dependency unless detection requires it.

### Why this cannot drop a true positive

Two axis-aligned rectangles A and B with non-zero intersection area
overlap in some `(x, y)` point. With cell width `w` and height `h`,
that point falls into cell `(floor(x/w), floor(y/h))`. Both A and B
are indexed under every cell their bounding box touches, so both
appear under that cell's occupant list, and the candidate generator
emits the pair `(i_A, i_B)`. The IoU predicate then re-checks the
pair. Filtering by co-cellular occupancy can only drop pairs that
do not intersect at all, which by definition cannot meet the
threshold.

The cell size choice (median width and height, floored at 1.0) is
robust. A larger cell does not change correctness; it only widens
the candidate set and reduces speedup. A smaller cell might cause a
true overlap to be missed only if `cell_w` or `cell_h` were zero,
which the floor guards against.

## Consequences

### Measured impact

Comparing v1.1.4 against v1.1.5 on the same four-density panel,
hardware unchanged (2 vCPU sandbox, 8 GB RAM):

| Fixture | v1.1.4 P50 | v1.1.5 P50 | Reduction |
|---|---:|---:|---:|
| white_paper_19p | 232 ms | 214 ms | 8% |
| clean_50p_native | 143 ms | 136 ms | 5% |
| safety_report_220p | 15,335 ms | 14,162 ms | 8% |
| gauntlet_metadata (forensic) | 4 ms | 4 ms | 0% (at floor) |

The dense 220-page case is the headline. cProfile attributes the
remaining ~14 seconds to `pymupdf.get_text("dict")` calls during
the per-analyzer page walk; that residue is the target of v1.1.6
(registry-level cost-class short-circuit) and a future
BatinObjectAnalyzer migration to the content index.

### Test posture

All 1,717 of 1,719 tests pass on the new branch. The two failing
tests (`text.homoglyph` fixture parametrizations in
`tests/application/test_scan_service.py` and `tests/test_fixtures.py`)
are pre-existing failures on the v1.1.4 main commit and are
unrelated to this change. A new property test
(`test_text_analyzer.py::test_overlapping_pair_candidates_superset`)
asserts that the candidate generator's output is a superset of any
pair that the naive O(n^2) scan would yield at IoU >= threshold,
across a panel of randomized span layouts.

### What this does not change

- Public API. `bayyinah.scan_file(...)` returns the same shape,
  same finding mechanisms, same severity tiers.
- Detection behaviour on the existing fixture corpus. Byte-identical.
- Memory footprint. The grid is a `dict[tuple[int, int], list[int]]`
  bounded by the number of spans on a page; on the densest pages of
  the safety report (~200 spans) this is a few kilobytes at most.

### What v1.1.6 will then close

Production-mode registry-level cost-class short-circuit. v1.1.4
short-circuited at the report-emission boundary; v1.1.6 pushes
that down into the registry so class-A mechanisms run first and
class-D analyzers never run when an earlier class trips a
verdict-determining finding. ADR-003 will record that decision.

## References

- v1.1.4 CHANGELOG `### Deferred to v1.1.5`, named items
- `analyzers/text_analyzer.py`, `_overlapping_pair_candidates`
- `docs/benchmarks/v1_1_5_rtree_spatial_index.py`, reproduction harness
- `docs/benchmarks/v1_1_5_rtree_spatial_index.md`, measured numbers
