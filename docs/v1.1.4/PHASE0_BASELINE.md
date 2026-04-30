# Phase 0 Baseline — pre-v1.1.4 profile

Recorded Apr 30 2026, 06:05 UTC, on the v1.1.4/content-index branch at the
base commit `2fc6a54` (155 mechanisms, 1,719 tests). The numbers below are
the reference against which the post-migration benchmarks are compared.

Hardware: Perplexity Computer sandbox, 2 vCPU, 8 GB RAM.

## Wall-clock (5 runs each, P50 median)

| Benchmark              | Pages | Size  | P50 (ms) | ms/page |
|------------------------|-------|-------|----------|---------|
| Bayyinah white paper   |  19   | 0.6 MB|     277  |   14.6  |
| NIST AI RMF            |  48   | 1.9 MB|   3,605  |   75.1  |
| arXiv LLM survey       | 140   | 5.8 MB|  50,588  |  361.3  |

The 220-page Intl AI Safety report did not complete in this run because the
arXiv survey ate the timeout. It will be measured in Phase 5.

## Where the cost lives (cProfile cumulative time)

### NIST 48p (cProfile total 4.5s)

| Hotspot                                | cumtime | share |
|----------------------------------------|---------|-------|
| `pymupdf get_text("dict")`             | 1.74s   | 38%   |
| `_scan_overlapping_spans`              | 1.72s   | 38%   |
| `_scan_raw_unicode` (per page re-walk) | 1.21s   | 27%   |
| `_scan_spans`                          | 1.13s   | 25%   |
| `_bbox_iou` (620,350 calls)            | 0.76s   | 17%   |
| `pdf_hidden_text_annotation`           | 0.09s   | 2%    |

Note: `get_text("dict")` is called 96 times for 48 pages, i.e. 2x per page.
The first call comes from `_scan_spans`, the second from `_scan_overlapping_spans`.
Halving these calls is the v1.1.4 ContentIndex contract.

### arXiv 140p (cProfile total 87.3s)

| Hotspot                                | cumtime | share |
|----------------------------------------|---------|-------|
| `_scan_overlapping_spans`              | 57.4s   | 66%   |
| `_bbox_iou` (36,753,258 calls)         | 45.3s   | 52%   |
| `_scan_raw_unicode`                    | 22.1s   | 25%   |
| `_scan_spans`                          | 3.9s    |  4%   |
| `JM_make_textpage_dict` (280 calls)    | 2.1s    |  2%   |
| `pdf_hidden_text_annotation`           | 1.4s    |  2%   |
| `_scan_annotations` (object_analyzer)  | 1.3s    |  2%   |

The class-C `overlapping_text` mechanism is the dominant cost on dense PDFs.
The R-tree spatial index that bounds this work is deferred to v1.1.5
(Phase 5 of SCALE_PLAN). For v1.1.4 the realistic gain on arXiv-class PDFs
is bounded by:

  - eliminating the 2x get_text duplicate (~1.5s)
  - unifying `_scan_raw_unicode` with the index walk (~20s)
  - flattening per-page recursion in span dispatch

That puts the v1.1.4 arXiv-class target in the 20-30s range, not the
1-3 seconds suggested by the original prompt. The big drop on arXiv-class
documents waits on v1.1.5 spatial indexing.

## v1.1.4 expected gains (per density class)

| Class       | Pre v1.1.4 P50 | v1.1.4 target | Mechanism                            |
|-------------|----------------|---------------|--------------------------------------|
| Synthesized | 277 ms         | <250 ms       | get_text halved, dispatch flattened  |
| Native text | 3,605 ms       | <1,000 ms     | get_text halved + raw-unicode unified|
| Dense LaTeX | 50,588 ms      | <30,000 ms    | get_text halved + raw-unicode unified|

The dense-LaTeX target is honest: the load-bearing class drops materially
but does not collapse until v1.1.5 ships the R-tree.

## Number of `get_text("dict")` calls per page

The cProfile ncalls column confirms the prompt hypothesis: every PDF is
walked twice today, once per `_scan_spans` and once per `_scan_overlapping_spans`.
v1.1.4 makes it once.

| Benchmark   | get_text calls | pages | calls/page |
|-------------|----------------|-------|------------|
| White paper |  38            |  19   |    2.0     |
| NIST        |  96            |  48   |    2.0     |
| arXiv       | 280            | 140   |    2.0     |
