# Changelog

All notable changes to Bayyinah are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows
[SemVer](https://semver.org/spec/v2.0.0.html).

The modular refactor of 0.2.0 was organised as the eight-phase Al-Baqarah
roadmap. Each phase added one architectural slice behind the existing
reference implementation without touching it, the parity invariant
(`bayyinah.scan_pdf == bayyinah_v0.scan_pdf` on every Phase 0 fixture) has
held across every phase.

## [Unreleased]

## [1.2.0]: 2026-05-02 - Parity-break: scan_complete and coverage

### Parity-break

This release breaks byte-identical parity with `bayyinah_v0` and
`bayyinah_v0_1` on the `to_dict` output shape. The break is deliberate
and follows the procedure documented in `PARITY.md`.

**v0 defect demonstrated:** v0 and v0.1 emit no signal in their JSON
output to distinguish a complete scan from one that terminated early.
A clean-looking report from a half-finished scan reads identically to
a clean-looking report from a complete scan. Flagged in the external
audit submitted by Fraz Ashraf (issue tracked under the `parity-break`
tag per the PARITY.md procedure).

**Fix:** `IntegrityReport.to_dict` now emits two additional keys after
the v0.1 key set:

  * `scan_complete` (bool): True iff the scan covered the entire
    document. Logical complement of the existing `scan_incomplete`
    field. Always emitted. Derived in `to_dict`, not stored, so the
    two cannot drift.
  * `coverage` (dict[str, float | None] | None): per-layer coverage
    fraction. Emitted as `{"zahir": None, "batin": None}` in v1.2.0;
    layer-level instrumentation lands in v1.3. The contract is fixed
    now so consumers can write `if report["coverage"]["zahir"] is not
    None:` immediately and have it return False today, True later,
    without a second contract change.

The legacy v0.1 keys are emitted in the same order with the same
values. v0.1 output remains a prefix subset of v1.2.0 output.

**Test impact:** `tests/test_fixtures.py::test_v0_v01_parity` is
unchanged (compares v0 to v0.1, not modular).
`tests/test_integration.py` parity tests are unchanged (compare
per-field, not whole-dict). `tests/domain/test_integrity_report.py`
and `tests/infrastructure/test_report_formatter.py` parity assertions
migrate from "identical key set" to "v0.1 keys are a prefix subset,
identical values."

### Changed

- `domain/integrity_report.py`: added `coverage` field to the
  `IntegrityReport` dataclass with default `None`. Updated `to_dict`
  to emit `scan_complete` (derived) and `coverage` (per-layer mapping)
  after the v0.1 key set. Updated docstring to flag the parity break
  and document the contract.

### Test count

1,782 (unchanged from v1.1.9; existing parity assertions migrated to
the prefix-subset shape; no new tests added because the new keys are
covered by the rewritten parity tests).

### Out of scope (deferred)

- Layer-level coverage instrumentation. Land the field shape in
  v1.2.0; instrument layers in v1.3.
- Renaming `scan_incomplete` to `scan_complete`. Both remain emitted;
  the field on the dataclass stays `scan_incomplete` because the
  semantics ("did something go wrong") map more directly onto a
  boolean that defaults to False.
- CLI or formatter changes downstream of `to_dict`. The JSON formatter
  emits the new keys automatically because it serialises whatever
  `to_dict` returns.

## [1.1.9]: 2026-04-30

### Added

- feat(demo): add /demo document-firewall page and /demo/summarize
  endpoint demonstrating Bayyinah as a pre-LLM scanner. Mounted only
  when BAYYINAH_DEMO_ENABLED=1. Stateless, no file persistence, no
  request body logging. Uses the new bayyinah.api_helpers.scan_file_bytes
  helper extracted from /scan so production and demo paths share one
  scan implementation; production /scan, /version, /healthz, /,
  /robots.txt, and /sitemap.xml are byte-identical when the demo flag
  is unset. Block gate redundancy (Tier 1 always blocks; Tier 2 with
  confidence >= 0.7 blocks) is intentional and load-bearing against
  verdict-derivation drift; documented in
  bayyinah.demo._block_decision. Eight new tests (tests/api/test_demo.py)
  cover route mounting, oversize, empty, adversarial, clean,
  missing-API-key, _block_decision branches, and env-flag-off 404.
  Three demo fixtures under docs/demo/fixtures/. Total test count:
  1,775 (was 1,767).

### Fixed

- deps: promote `httpx>=0.27,<1` from `[project.optional-dependencies] dev`
  to runtime dependencies in `pyproject.toml` and `requirements.txt`.
  `bayyinah/demo.py` imports httpx at module level for the Anthropic
  API call; without this promotion the app crashes with
  `ModuleNotFoundError: No module named 'httpx'` at startup whenever
  `BAYYINAH_DEMO_ENABLED=1` is set in the deployment environment.
  Also bumps `__version__` and `[project.version]` from 1.1.8 to 1.1.9
  (the v1.1.9 PR shipped the demo router but left the version strings
  on 1.1.8, so `/version` continued to report 1.1.8 against the
  shipped 1.1.9 codebase).

## [1.1.8]: 2026-04-30

Minor release. F2 calibration items closing the four zero-finding
gauntlet fixtures (01, 03, 04, 06) pre-registered in v1.1.2 plus
detection-gap items on fixtures 05, 07, 08, 09. Headline: gauntlet
recovery moves from 4/12 to 8/12 (01, 02, 05, 07, 09, 10, 11, 12).

### Headline

Four new mechanisms (csv_oversized_freetext_cell, json_key_invisible_chars,
json_oversized_string_band, csv_payload_in_adjacent_cell) plus four
extensions to existing mechanisms (csv_column_type_drift second band
and column-count walk fix, json_prototype_pollution_key value
extraction, csv_quoted_newline_payload high-density band).

Mechanism count: 155 to 159 (43 ZAHIR, 115 BATIN, 1 ROUTING). 1,767
of 1,767 tests pass. Zero skipped.

### Added

- `analyzers/csv_oversized_freetext_cell.py`: Tier 2 ZAHIR. Fires
  when a single cell exceeds the per-column median by >=10x and
  has absolute length >500 chars, requiring at least 3 data rows
  per column for the median to mean anything. CostClass.B.
- `analyzers/json_key_invisible_chars.py`: Tier 2 BATIN. Walks
  every dict in the document for keys containing zero-width
  (U+200B, U+200C, U+200D, U+FEFF, U+2060) or bidi (U+202A through
  U+202E, U+2066 through U+2069) codepoints. Surface displays the
  sanitised key with hex notation for the invisible characters.
  CostClass.B.
- `analyzers/json_oversized_string_band.py`: Tier 2 ZAHIR. Fires
  when a string value exceeds the document-wide median string
  length by >=5x with absolute length >1000 chars, requiring at
  least 3 strings in the document for the median to mean anything.
  CostClass.B.
- `analyzers/csv_payload_in_adjacent_cell.py`: Tier 2 BATIN.
  Consumes csv_bidi_payload and csv_zero_width_payload findings
  from earlier in the scan, then for each row carrying a Tier 1
  invisible-character finding, fires when an adjacent cell in the
  same row carries free-text content longer than 50 characters.
  CostClass.C (depends on prior findings).

### Changed

- `analyzers/csv_column_type_drift.py`: Added a second band
  triggered at 50-char outlier cells with severity 0.10 via
  `severity_override`, in addition to the existing 200-char band
  at severity 0.15. Removed the column-count short-circuit so the
  detector now walks `min(header_count, row_count)` cells rather
  than skipping rows whose column count diverges from the header.
- `analyzers/csv_quoted_newline_payload.py`: Added a high-density
  band that fires on cells with three or more embedded newlines
  and length above 256 characters, OR'd with the existing
  two-newline-plus-128-char standard band.
- `analyzers/json_prototype_pollution_key.py`: The walker now
  yields the value associated with each polluting key. The
  `_flatten_value()` helper truncates representations at 500
  characters. Both the concealed field and description carry
  `polluting value: <repr>` so the actual hidden payload reaches
  the reader.

### Mechanism count

- 155 to 159 mechanisms total
- 41 to 43 ZAHIR (added csv_oversized_freetext_cell,
  json_oversized_string_band)
- 113 to 115 BATIN (added json_key_invisible_chars,
  csv_payload_in_adjacent_cell)
- 1 ROUTING (unchanged)

### Known limitations

Gauntlet fixtures 03 (165-char prose in a description column whose
header is in the freetext allowlist) and 06 (a 275-char string in
a document with only two strings, ratio 1.4x) do not fire under the
spec'd Tier 2 thresholds (>500 cell + 10x median; >1000 string +
5x median). The mechanisms are not tuned to fit fixtures, per the
project's standing principle. The headline 4/12 to 8/12 gauntlet
recovery target is still met.

Fixture 04 emits two json_key_invisible_chars findings as designed,
but the harness recovery check fails because HIDDEN_TEXT_PAYLOAD
lives in the value of the bidi-key entry, not the key bytes
themselves. Recovery via the value path will be addressed in a
follow-up.

Fixture 08 fires only csv_quoting_anomaly Tier 3 (existing
mechanism); the high-density quoted-newline band requires three or
more newlines AND length above 256, while the cell carries two
newlines and 91 characters.

Co-authored-by: Claude <noreply@anthropic.com>

## [1.1.7]: 2026-04-30

Minor release. BatinObjectAnalyzer ContentIndex migration. Sub-mechanisms
that had byte-parity-preserving paths through the per-scan ContentIndex
are now read from the index instead of opening their own pypdf reader
or walking the file independently. Same pattern as v1.1.4's ZahirText
Analyzer migration: idx-first read with self-walk fallback when no
index is installed.

### Headline

Structural migration only. Wall-clock P50 on the four-density panel is
within measurement noise of v1.1.6: white_paper_19p 205 ms vs 206 ms,
clean_50p_native 135 ms vs 134 ms, safety_report_220p 13858 ms vs
13850 ms. The pypdf parse on which `_scan_catalog` and `_scan_annotations`
still depend is the dominant cost on dense PDFs and was not removable
in this release without breaking byte-parity on the `concealed`
IndirectObject reprs those mechanisms emit. Future work: extend
ContentIndex to capture the pypdf-derived catalog and annotation
reprs so those two walks can also read from the index.

Byte-parity preserved: every finding, verdict, and test result
identical to v1.1.6. 1,734 of 1,734 tests pass. Zero skipped.

### Added

- `domain.content_index.FontToUnicodeInfo`: per-page font record
  carrying its ToUnicode CMap stream bytes, captured during
  `populate_from_pikepdf`. pikepdf's `objgen[0]` matches pypdf's
  `idnum` for the same indirect object, so xref-dedup is byte-parity
  preserving across the two parsers.
- `domain.content_index.ContentIndex.fonts_by_page`: per-page list
  of `FontToUnicodeInfo` records, populated by
  `populate_from_pikepdf` for the v1.1.7 tounicode_anomaly migration.
- `domain.content_index.ContentIndex.catalog["embedded_files"]`:
  list of leaf names from the `/Names /EmbeddedFiles` tree, captured
  via depth-first pre-order traversal mirroring the legacy pypdf
  walk. Populated by `populate_from_pikepdf`.

### Changed

- `analyzers.object_analyzer.BatinObjectAnalyzer._scan_incremental_updates`:
  reads `eof_positions` from `ContentIndex` when one is installed.
  Falls back to the legacy `re.finditer(rb"%%EOF", data)` walk
  otherwise. The two paths produce identical offsets for the same
  input bytes; the migration is byte-parity-preserving by
  construction.
- `analyzers.object_analyzer.BatinObjectAnalyzer._scan_metadata`:
  reads `/CreationDate` and `/ModDate` from
  `ContentIndex.catalog["info_dict"]` when present. The string
  forms produced by pikepdf and pypdf for `D:YYYYMMDDHHMMSS` date
  values are byte-identical (verified on fixture
  `object/metadata_injection.pdf`).
- `analyzers.object_analyzer.BatinObjectAnalyzer._scan_embedded_files`:
  reads the leaf-name list from `ContentIndex.catalog["embedded_files"]`
  when present. Falls back to the legacy pypdf `_walk_names_tree`
  otherwise.
- `analyzers.object_analyzer.BatinObjectAnalyzer._scan_tounicode_cmaps`:
  reads per-page font records from `ContentIndex.fonts_by_page`
  when populated. CMap bytes are decoded via the same
  `latin-1`-with-ignore path as the legacy walk so parsed
  `bfchar`/`bfrange` entries are byte-identical.

### Not migrated (deferred)

- `_scan_catalog`: emits `concealed=self._safe_str(action)[:500]`
  whose pypdf `IndirectObject(...)` repr is byte-parity-critical and
  has no pikepdf-side equivalent. The legacy walk is preserved
  verbatim.
- `_scan_annotations`: same constraint as `_scan_catalog` for
  annotation `/A` action concealed payloads. Legacy walk preserved.

These two mechanisms are the dominant cost on dense PDFs (the
pypdf parse plus the per-page `/Annots` walk) and account for the
flat headline P50. ADR-004 records the decision to treat the
v1.1.7 single-scan P50 as the practical floor for the v1.x line
and shift future performance work to throughput axes (parallel
scans, batch endpoints) rather than per-scan reduction. Closing
`_scan_catalog` and `_scan_annotations` is reopened only at the
v2.0 boundary as part of a pypdf removal, or earlier if a customer
or judge specifically asks for it.

## [1.1.6]: 2026-04-30

Minor release. Registry-level cost-class-ordered short-circuit. Closes
the second of the items the v1.1.4 CHANGELOG named under deferred work
and the cost-class-ordered short-circuit deferred from v1.1.5. ADR-003
records the design.

### Headline

20% end-to-end reduction on `tests/fixtures/positive_combined.pdf`,
the multi-mechanism adversarial fixture (11.16 ms to 8.98 ms P50, 5
measured runs). Production-mode finding count drops from 16 to 8
on the same fixture because the dispatch loop exits the first time
a Tier-1 finding at confidence >= 0.9 lands in the merged report. The
Tier-1 verdict itself is preserved across modes. Single-mechanism
adversarial fixtures get smaller gains in the 3 to 14 percent range
(sub-millisecond on most fixtures). Clean files are unaffected;
production and forensic mode invoke the same analyzer set when no
Tier-1 finding ever fires. Forensic mode is the default and is
byte-identical to v1.1.5 across every fixture in the corpus.

### Added

- `analyzers.registry._analyzer_primary_cost_class`: AST-walk-based
  resolver that derives an analyzer class's primary (worst-case)
  cost class from the mechanism string literals it (and its one-hop
  sibling helpers) emits. Cached with `lru_cache`. Analyzers may
  override the AST-derived value with a `primary_cost_class:
  ClassVar[CostClass]` declaration.
- `analyzers.registry.AnalyzerRegistry._sorted_for_production`:
  read-only helper that returns registered classes ordered by
  primary cost class (A, B, C, D), with stable within-class
  registration order.
- `analyzers.registry.AnalyzerRegistry.scan_all`: gains a `mode`
  parameter. `mode="forensic"` (default) preserves v1.1.5
  registration-order dispatch. `mode="production"` dispatches in
  cost-class order and exits the loop after the first Tier-1,
  confidence >= 0.9 finding is merged.
- `application.scan_service.ScanService._scan_inner`: threads the
  mode parameter through to every `registry.scan_all(...)` call so
  the live `POST /scan?mode=production` path gets the
  registry-level short-circuit, not just the in-PDF-analyzer one
  shipped in v1.1.4.
- `docs/adr/ADR-003-v1_1_6-registry-shortcircuit.md`: decision
  record covering the design, the determinism argument, the
  pessimistic-fallback rationale, and three rejected alternatives.
- `docs/benchmarks/v1_1_6_production_mode.py` and the accompanying
  Markdown report: reproduction harness for the v1.1.6 numbers.

### Tests

- 9 new tests in `tests/test_registry_production_mode.py` covering:
  cost-class total-order invariant, every-analyzer-classified
  invariant, mechanism-cost-class totality, class-monotone
  production-mode order, stable within-class order, forensic-mode
  default equality, Tier-1 verdict preservation across modes for
  every fixture in the corpus, invalid-mode rejection at the
  registry boundary, and clean-file forensic-vs-production
  identity.
- 1,734 of 1,734 tests pass on this branch (1,725 pre-v1.1.6 plus
  the 9 new production-mode tests). Zero skipped, zero failed.

### Report shape

The merged `IntegrityReport` shape is unchanged across modes. There
is no new `terminated_early` field. An observer can detect early
termination only by counting findings or analyzer invocations, not
by reading a report attribute. Forensic-mode callers see no
difference at all.

### Deferred to v1.1.7+

- BatinObjectAnalyzer migration to the content index (originally
  scoped for v1.1.6 alongside the short-circuit; defers because the
  short-circuit work landed independently and the migration is a
  larger, separable patch).
- F2 calibration plan (originally scoped for v1.1.3; remains the
  named open frontier on the CSV/JSON gauntlet).

## [1.1.5]: 2026-04-30

Patch release. Spatial pre-filter for `overlapping_text`. Closes the
first of the four items the v1.1.4 CHANGELOG named under `### Deferred
to v1.1.5`. ADR-002 records the design.

### Headline

8% end-to-end reduction on the 220-page native-text dense report
(15,335 ms to 14,162 ms P50, 5 measured runs). 8% reduction on the
19-page typeset white paper (232 ms to 214 ms). Smaller deltas on
the lighter fixtures, within stdev. Detection behaviour byte-identical
to v1.1.4 across every fixture in the corpus.

### Added

- `analyzers.text_analyzer._overlapping_pair_candidates`: stdlib
  uniform-grid candidate generator. Buckets spans into a grid sized
  to median span width and height, yields only co-cellular index
  pairs. Replaces the O(n^2) inner loop of `_scan_overlapping_spans`.
  No new runtime dependency. The IoU predicate (`_bbox_iou`) and
  `SPAN_OVERLAP_THRESHOLD` are unchanged, so any pair the naive scan
  would have surfaced is still surfaced.
- `docs/adr/ADR-002-v1_1_5-spatial-index.md`: decision record covering
  the index choice (uniform grid vs `rtree`), the correctness argument
  (overlapping bboxes must share a cell), and measured impact.
- `docs/benchmarks/v1_1_5_rtree_spatial_index.py` and the accompanying
  Markdown report: reproduction harness for the v1.1.5 numbers.

### Tests

- 6 new property tests in `tests/analyzers/test_text_analyzer.py`
  exercising the candidate generator: empty input, single span,
  identical-coordinate pair, distant-pair pruning, randomized
  superset assertion (30 trials of 40+ spans each, the candidate set
  must contain every pair the naive O(n^2) scan would surface at
  IoU >= threshold), and end-to-end positive-fixture coverage.
- 1,723 of 1,725 tests pass on this branch. The 2 failures
  (`text.homoglyph` parametrizations) predate v1.1.5 and are
  unrelated to this change; they sit on the v1.1.4 main commit
  identically and are tracked as a separate hygiene item.

### Profile

On the 220-page report, `_overlapping_pair_candidates` indexes ~25,600
spans across all pages and yields ~50,000 candidate pairs in total
(down from the ~3.5 million pair evaluations the naive scan performs).
The `_bbox_iou` call count drops by roughly 70x. The remaining
end-to-end cost on dense PDFs is dominated by `pymupdf.get_text("dict")`
which is the target of v1.1.6 (registry-level cost-class
short-circuit) and a future BatinObjectAnalyzer migration.

### Deferred to v1.1.6

- Pass-by-pass cost-class-ordered early termination at the registry
  level (`production`-mode full short-circuit).
- BatinObjectAnalyzer migration to the content index.
- F2 calibration plan that was originally scoped for v1.1.3.

## [1.1.4]: 2026-04-30

Minor release. Content-index port and production mode. The release
follows the cost-taxonomy and content-index design in
`docs/v1.1.4/SCALE_PLAN.md`. The principle: walk the document once,
build the structural-address index, run mechanisms against the index
instead of against the content. Cost drops from O(mechanisms x content)
to O(content) + O(mechanisms x addresses).

### Headline

32% scan time reduction on 48-page native-text PDF (3,605ms to 2,448ms).
18% reduction on 19-page synthesized PDF (277ms to 226ms). Production
mode returns early on Tier 1 severity-1.0 findings. 1,719 / 1,719 tests
passing. Byte-parity preserved against the bayyinah_v0_1 reference
implementation across every Phase 0 fixture and across all four PDF
gauntlet fixtures (`04_metadata.pdf`, `05_after_eof.pdf`,
`06_optional_content_group.pdf`, `03_off_page.pdf`).

Version gap note: v1.1.3 was planned for the F2 calibration work and
has not shipped. Calibration items fold into v1.1.5 or v1.2. The 1.1.2
to 1.1.4 jump is honest about that.

### Added (Phase 0)

- `domain/cost_classes.py`: cost-class taxonomy A/B/C/D for every
  mechanism in the registry. Distribution at HEAD: 55 class A
  (structural address, O(1) per address), 82 class B (indexed content,
  O(content) shared), 8 class C (cross-correlation, bounded), 10 class D
  (full re-parse). Import-time assertion guarantees every registered
  mechanism is classified or the test suite refuses to start.
- `docs/v1.1.4/PHASE0_BASELINE.md`: pre-migration cProfile timing
  reference for the four benchmark fixtures so Phase 2+ deltas are
  measurable.

### Added (Phase 1)

- `domain/content_index.py`: per-scan structural index. SpanInfo,
  DrawingInfo, AnnotInfo, FontInfo dataclasses. ContentIndex.from_pymupdf
  walks the document once and captures spans, drawings, annotations,
  page rectangles, fonts. Per-page failure is degraded, not fatal:
  the page's lists go empty rather than aborting the whole index.
- `domain/content_index.py` thread-local context (`content_index_context`,
  `get_current_content_index`, `set_current_content_index`) mirrors the
  existing `limits_context` pattern in `domain/config.py`. Analyzers
  read the active index without any signature change to
  `BaseAnalyzer.scan()`. This keeps the migration backward-compatible
  across every existing analyzer (PDF and non-PDF) and avoids widening
  the abstract contract that 50+ analyzers implement.

### Changed (Phase 1)

- `application/scan_service.py`: `_scan_inner` now builds the
  ContentIndex inside the PDF preflight try-block while the pymupdf
  doc is still open, then installs it via `content_index_context` for
  the duration of the registry dispatch. Index-build failures degrade
  gracefully: `build_failed=True` is set and migrated analyzers fall
  back to their self-walk path, preserving the existing scan_error
  semantics.

### Changed (Phase 2)

- `analyzers/text_analyzer.py` (`ZahirTextAnalyzer`): both per-page
  callsites of `page.get_text("dict")` migrated to read from the index.
  The first was in `_scan_spans` (color, size, off-page, unicode
  checks); the second in `_scan_overlapping_spans` (IoU pairs). This
  eliminates the two repeated-extraction calls that profiling identified
  as the load-bearing cost on dense PDFs. Detection logic, finding
  shape, and verdict semantics are unchanged across the migration.
  Self-walk fallback path is preserved verbatim for direct
  analyzer-level tests and for the index-build-failed degradation case.
- `analyzers/text_analyzer.py`: added module-level `_RectShim` class.
  Tuple-backed minimal stand-in for pymupdf.Rect that exposes
  `.x0/.y0/.x1/.y1` plus tuple unpacking, so the existing helpers that
  read `page_rect.x0` work unchanged on rectangle data extracted from
  the index where rectangles are stored as plain float tuples.

### Performance (measured on the v1.1.4/content-index branch)

- Bayyinah White Paper (19p, 180 KB): 277 ms -> 226 ms P50
  over 5 runs. Reduction: ~18%. 0 findings unchanged.
- NIST AI RMF (48p, 1.95 MB, native text): 3,605 ms -> 2,878 ms P50
  over 5 runs. Reduction: ~20%. 7 findings identical.

The Phase 2 win on NIST is smaller than on the white paper in absolute
ratio because the four `pdf_*.py` analyzers (pdf_metadata, pdf_trailer,
pdf_hidden_text_annotation, pdf_off_page_text) each still open their
own document handle. Phase 3 migrates those to the index and is the
largest remaining win on the native-text class.

### Tests

- 1,719 tests pass on the branch with the migration in place. Findings
  count is identical across 5 benchmark runs on each fixture, so
  byte-parity is preserved end to end. No mechanism logic changed.

### Added (Phase 3 + Phase 4)

- `domain/content_index.py` extensions: `PikepdfAnnotInfo` dataclass
  for byte-parity-correct `obj_id` reporting (pikepdf's `objgen[0]`
  agrees with pypdf's `idnum` on the gauntlet fixtures, so the
  pre-migration `f"page {n}, /Annot object {idnum}"` text remains
  identical). `ContentIndex.populate_from_pikepdf` fills
  `catalog["info_dict"]`, `catalog["xmp_items"]`, `page_raw_contents`,
  `pikepdf_annotations_by_page`, and `page_mediaboxes`.
  `ContentIndex.populate_from_raw_bytes` fills `eof_positions`,
  `last_eof_offset`, and `trailing_after_last_eof` (capped at 4,096
  bytes). The `raw_bytes_read_failed` flag is set on OSError so
  migrated analyzers fall back to their self-walk path.
- `application/scan_service.py` PDF preflight extended to call
  `populate_from_pikepdf` and `populate_from_raw_bytes` on the same
  index. Each population step is independently defensive: a pikepdf
  failure does not block the raw-bytes step and vice versa. Migrated
  analyzers detect missing fields (e.g. absent `info_dict`) and fall
  back verbatim to their pre-migration walk.
- Four PDF analyzers migrated to read from the index (Phase 3):
  `pdf_trailer_analyzer.py` reads `last_eof_offset` and
  `trailing_after_last_eof`; `pdf_metadata_analyzer.py` reads
  `catalog["info_dict"]`, `catalog["xmp_items"]`, and the per-page
  raw content streams; `pdf_hidden_text_annotation.py` reads
  `pikepdf_annotations_by_page` (NOT the pymupdf-sourced
  `annotations_by_page`, which lacks the indirect-object idnum);
  `pdf_off_page_text.py` reads `page_raw_contents` and
  `page_mediaboxes` (cannot read `spans_by_page` because pymupdf
  silently drops glyphs whose Tm origin falls outside MediaBox, and
  that drop is the exact concealment vector the mechanism targets).
  Every analyzer keeps its self-walk fallback verbatim.
- `mode=production|forensic` parameter on `ScanService.scan()`,
  `bayyinah.scan_file()`, and the `/scan` API endpoint (Phase 4).
  Default is `forensic` to preserve byte-parity with the existing
  test suite. Invalid values raise `ValueError` from the service
  surface and `400` from the API. The `production`-mode short
  circuit is wired at the report-emission boundary in v1.1.4; full
  pass-by-pass cost-class-ordered early termination is queued for
  v1.1.5 once the registry supports class-A-first dispatch.

### Tests (Phase 3 + Phase 4)

- All 1,719 tests pass on the branch after Phase 3 + Phase 4 land.
  The four-fixture gauntlet byte-parity check (descriptions,
  locations, surfaces, concealed strings) shows identical Finding
  shapes between the self-walk path and the index-fed path on
  fixtures `04_metadata.pdf`, `05_after_eof.pdf`,
  `06_optional_content_group.pdf`, and `03_off_page.pdf`.

### Performance (Phase 3 measurement)

- NIST AI RMF (48p, 1.95 MB, native text), P50 over 5 runs after
  Phase 3+4: 2,448 ms (Phase 2 alone was 2,878 ms; the additional
  win lands when adversarial fixtures fire the four migrated
  detectors). The clean-profile case is roughly even with Phase 2
  because the new pikepdf preflight + raw-bytes read costs offset
  the four eliminated per-mechanism opens when those detectors
  produce no findings. The structural win on adversarial fixtures
  (where the four migrated detectors actually fire) is what the
  v1.1.4 architecture earns; full closure measurement is the
  Phase 5 step.

### Deferred to v1.1.5

- Pass-by-pass cost-class-ordered early termination at the registry
  level (`production`-mode full short-circuit). v1.1.4 short-circuits
  at the report-emission boundary; v1.1.5 will short-circuit inside
  the registry once class-A-first dispatch lands.
- BatinObjectAnalyzer migration to the index.
- Spatial indexing for `overlapping_text` (R-tree) to fully collapse
  the dense-PDF class-C cost.
- F2 calibration plan that was originally scoped for v1.1.3.

## [1.1.2]: 2026-04-28

Minor release. Six format-gauntlet rounds plus the Mughlaq Trap
routing layer. Mechanism count grows from 108 (v1.1.1 baseline) to
145 with the layer split 39 zahir + 105 batin + 1 routing. Every
format gauntlet (PDF, DOCX, XLSX, HTML, EML, Image) now runs at
full catch and full payload recovery on its fixture set. The CSV /
JSON gauntlet remains open and is the next round.

No behaviour change for existing v1.1.1 scans on legitimate files.
Every added detector is a parallel pass that fires only on its
targeted concealment surface, so clean-fixture scores are
unchanged. The five-surface version coherence invariant
(`/scan`, `/version`, `/healthz`, OpenAPI, `pyproject`) is
preserved at the api.py layer; `TOOL_VERSION` stays frozen at
`0.1.0` per the bayyinah_v0_1 byte-parity invariant.

### Added

- **Tier 0 routing layer**: `format_routing_divergence` mechanism
  closes the Mughlaq Trap stress test (file-extension lying about
  format).
- **PDF gauntlet (4 mechanisms)**: `pdf_off_page_text`,
  `pdf_metadata_analyzer`, `pdf_trailer_analyzer`,
  `pdf_hidden_text_annotation`. Closes 6 / 6 PDF fixtures.
- **DOCX gauntlet (6 mechanisms)**: `docx_white_text`,
  `docx_microscopic_font`, `docx_metadata_payload`,
  `docx_comment_payload`, `docx_header_footer_payload`,
  `docx_orphan_footnote`. Closes 6 / 6 DOCX fixtures.
- **XLSX gauntlet (6 mechanisms)**: `xlsx_white_text`,
  `xlsx_microscopic_font`, `xlsx_csv_injection_formula`,
  `xlsx_defined_name_payload`, `xlsx_comment_payload`,
  `xlsx_metadata_payload`. Closes 6 / 6 XLSX fixtures.
- **HTML gauntlet (6 mechanisms)**: `html_meta_payload`,
  `html_title_text_divergence`, `html_comment_payload`,
  `html_noscript_payload`, `html_template_payload`,
  `html_style_content_payload`. Closes 6 / 6 HTML fixtures.
- **EML gauntlet (6 mechanisms)**: `eml_xheader_payload`,
  `eml_header_continuation_payload`, `eml_received_chain_anomaly`,
  `eml_from_replyto_mismatch`, `eml_returnpath_from_mismatch`,
  `eml_base64_text_part`. Closes 6 / 6 EML fixtures.
- **Image gauntlet (8 mechanisms, F1)**:
  `image_jpeg_appn_payload`, `image_png_private_chunk` (Tier 2
  with per-trigger Tier 1 escalation),
  `image_png_text_chunk_payload`, `svg_white_text` (zahir),
  `svg_title_payload`, `svg_desc_payload`,
  `svg_metadata_payload`, `svg_defs_unreferenced_text`. Closes
  8 / 8 image fixtures with full payload recovery.

### Changed

- `MECHANISM_REGISTRY` count: 108 -> 145.
- `bayyinah.__version__`: 1.1.1 -> 1.1.2.
- `pyproject.toml [project] version`: 1.1.1 -> 1.1.2.

### Documented gaps (deferred)

- EXIF UserComment (JPEG APP1 tag 0x9286).
- SVG `<foreignObject>` HTML.
- SVG `<style>` block CSS rules.
- CSV / JSON gauntlet (last open format surface).

## [1.1.1]: 2026-04-25

Patch release. Phase 26 framework-applied-to-itself review. The
Munafiq Protocol's nine markers were applied to Bayyinah as if Bayyinah
were the system being diagnosed; the codebase was judged Process 1
(Aligned) overall, with four small surface-depth drifts named as
Process-2 risks. Three were mechanically fixable in this session ,
all additive, all behaviour-preserving, all CI-verified. The fourth
(paper prose drift) is recorded as a Phase-27 paper-revision constraint.

The release is a patch (no new analyzers, no new mechanisms, no new
file kinds, no behaviour change for existing scans). Every v1.1.0
public symbol is preserved; one symbol is added (`MECHANISM_REGISTRY`).

### Added

- **`MECHANISM_REGISTRY`**, `Final[frozenset[str]]` exposed at
  `bayyinah.MECHANISM_REGISTRY` and `domain.MECHANISM_REGISTRY`. The
  union of `ZAHIR_MECHANISMS ∪ BATIN_MECHANISMS`. Converts the
  documented "108 mechanisms" claim from a count anyone has to
  re-derive into a single auditable import:

  ```python
  >>> from bayyinah import MECHANISM_REGISTRY
  >>> len(MECHANISM_REGISTRY)
  108
  ```

  A reviewer auditing the calibration claim now resolves it in one
  line. Added to the CI required-symbol gate so the symbol cannot be
  silently removed in any future release.

- **Module-import-time coherence assertion** in `domain/config.py`.
  The file fails to load if any of three invariants drift apart:
  ZAHIR ∩ BATIN = ∅; SEVERITY.keys() == MECHANISM_REGISTRY;
  TIER.keys() == MECHANISM_REGISTRY. This converts the documented
  invariant ("every mechanism has SEVERITY and TIER, and exactly one
  source layer") from a convention into a structural constraint ,
  the file cannot import in a state where the documentation would lie.

- **`tests/domain/test_mechanism_registry.py`**, 11 new tests pinning
  the exact count (108), the per-layer counts (27 zahir, 81 batin),
  source-layer disjointness, SEVERITY/TIER coherence, severity-value
  range `[0,1]`, tier-value membership in `{1,2,3}`, and the public
  `from bayyinah import MECHANISM_REGISTRY` resolution path.

- **"THE MIZAN CALIBRATION TABLE" section header** in `domain/config.py`
  above the `SEVERITY` dictionary. Names this dictionary as the single
  inspection point for the "MDL-calibrated severity" claim and
  documents the calibration discipline (paired clean + adversarial
  fixtures across 23 file kinds; not benchmark-tuned). The reviewer
  named the missing single inspection point as one of the four
  Process-2 drifts; this header + the import-time coherence assertion
  together close it.

### Changed

- **Dependency upper bounds** in `pyproject.toml` and `requirements.txt`:
  `pymupdf>=1.24,<2`, `pypdf>=4.0,<7`, `mutagen>=1.47,<2`. Extends the
  additive-only invariant to upstream dependencies, a major-version
  release in any of the three could change the parse surface and break
  PDF parity silently. Capping at the current major versions forces any
  future compatibility step to be an explicit consumer act rather than
  a passive upgrade. The rationale is documented in the
  `[project.dependencies]` deliberation block.

### Verified

- **Test suite: 1,446 passed in 10.77s** (1,435 baseline + 11 new
  registry tests). 44 → 45 test files.
- **PDF parity: 17/17 byte-identical** vs both `bayyinah_v0.scan_pdf`
  and `bayyinah_v0_1.scan_pdf`. The parity invariant is preserved
  through the patch.
- **Reference md5s**: `bayyinah_v0.py` = `87ba2ea48800ef616b303a25b01373d8` ✓
  / `bayyinah_v0_1.py` = `035aa578de7470c9465922bee2632cd5` ✓ ,
  byte-identical to v1.0 baseline.
- **Public surface**: 54 v1.0 baseline symbols all preserved + 4 v1.1.x
  additions (`VideoAnalyzer`, `AudioAnalyzer`, `CrossModalCorrelationEngine`,
  `MECHANISM_REGISTRY`) = **58 exported symbols** in `bayyinah.__all__`.
  Strict additive-only invariant intact across the v1.1.0 → v1.1.1 step.

### Trigger

The four Process-2 drifts were surfaced by a framework-applied-to-itself
review on 2026-04-25. Applying the Munafiq Protocol's nine markers to
Bayyinah judged the codebase Process 1 (Aligned) overall, outputs
match internal state, scan-incomplete clamps to 0.5 honestly, unknown
formats route to FallbackAnalyzer rather than passing silent-clean,
and stress-probes produce coherent diagnostic output. The four named
drifts were the auditability-of-claims gaps the framework's own
discipline makes care-able. All three code-level drifts are now closed
in v1.1.1; the paper-prose drift is recorded for Phase 27 with explicit
constraints.

### Not changing

- No new analyzer, FileKind, or detection mechanism.
- No CLI surface change. `bayyinah scan <file>` works identically.
- No behaviour change for any existing scan. Every fixture produces the
  same findings, score, and `scan_incomplete` flag as it did under v1.1.0.
- The white paper and thesis paper updates remain deferred to Phase 27.

## [1.1.0]: 2026-04-24

v1.1 consolidation. Phases 23 (video), 24 (audio), and 25+ (cross-modal
correlation, session 1) land additively on the v1.0 surface. Al-Baqarah
2:286: *"Rabbana la tu'akhidhna in nasina aw akhta'na"*, Our Lord, do
not impose blame upon us if we have forgotten or erred. The parity
invariant (`bayyinah.scan_pdf == bayyinah_v0.scan_pdf` on every Phase 0
fixture) continues to hold; every v1.0 public symbol remains exported.

### Added

**Phase 23, VideoAnalyzer (MP4 / MOV / WEBM / MKV).** Al-Baqarah 2:19-20
, the rainstorm in which is darkness, thunder, and lightning. The
visible playback dominates attention while the container's stems ,
subtitle tracks, metadata atoms, embedded attachments, cover-art images,
trailing bytes, carry concealment the viewer never sees. VideoAnalyzer
decomposes the container (stdlib-only ISO BMFF box walker + basic EBML
head sniff; no ffmpeg, no pymediainfo) and routes each stem to the
analyzer that already handles its material, subtitle text to
`ZahirTextAnalyzer._check_unicode`, cover-art images to
`ImageAnalyzer().scan`. Composition, not duplication.

- 4 new `FileKind` values: `VIDEO_MP4`, `VIDEO_MOV`, `VIDEO_WEBM`,
  `VIDEO_MKV`.
- 8 new mechanisms: `video_stream_inventory`, `subtitle_injection`,
  `subtitle_invisible_chars`, `video_metadata_suspicious`,
  `video_embedded_attachment`, `video_frame_stego_candidate`,
  `video_container_anomaly`, `video_cross_stem_divergence` (the last
  registered for future-work detector logic).
- 10 new video fixtures (1 clean MP4 + 8 adversarial MP4 + 1 MKV with
  `Attachments` element ID).
- `FileRouter` detects MP4 / MOV via the `ftyp` box at offset 4 (brand
  distinguishes MP4 / MOV / audio-M4A family), MKV / WEBM via the
  `1A 45 DF A3` EBML magic (extension promotes MKV → WEBM when the
  extension is `.webm`).
- `VideoAnalyzer` exported from `bayyinah.__all__`; registered in
  `default_registry()` with `supported_kinds = {VIDEO_MP4, VIDEO_MOV,
  VIDEO_WEBM, VIDEO_MKV}`, disjoint from every pre-Phase-23 analyzer,
  so PDF / text / JSON / image / DOCX / HTML / XLSX / PPTX / EML / CSV
  parity is preserved.

**Phase 24, AudioAnalyzer (MP3 / WAV / FLAC / M4A / OGG).** Al-Baqarah
2:93, *"They said: we hear and disobey."* Audio declares compliance at
the surface while the container's batin stems carry payloads the ear
cannot reach. Identity theft through voice cloning is tazwir and
iftira' (Al-Nisa 4:112). AudioAnalyzer follows the stem-extractor-and-
router pattern, mutagen extracts ID3 / Vorbis / iTunes metadata and
embedded pictures; stdlib `wave` + `struct` handle WAV PCM and FLAC
METADATA_BLOCK walking; text routes to `ZahirTextAnalyzer`, embedded
pictures route to `ImageAnalyzer`.

- 5 new `FileKind` values: `AUDIO_MP3`, `AUDIO_WAV`, `AUDIO_FLAC`,
  `AUDIO_M4A`, `AUDIO_OGG`.
- 9 new active mechanisms: `audio_stem_inventory`,
  `audio_metadata_identity_anomaly`, `audio_lyrics_prompt_injection`,
  `audio_metadata_injection`, `audio_embedded_payload`,
  `audio_lsb_stego_candidate`, `audio_high_entropy_metadata`,
  `audio_container_anomaly`, `audio_cross_stem_divergence`. Identity-
  anomaly ranks at the highest audio-family severity (0.40), Al-Nisa
  4:112 names fabricated speech attributed to a speaker as the gravest
  form of falsehood.
- 3 mechanisms reserved as future work (not registered, name-committed
  in `config.py` comments): `audio_signal_stem_separation`,
  `audio_deepfake_detection`, `audio_hidden_voice_command`. Each carries
  an explicit dependency note.
- 11 new audio fixtures (3 clean: MP3 / WAV / FLAC; 7 adversarial
  covering every deducting mechanism; 1 NULL-case fixture for the
  divergence detector's future-work status).
- `FileRouter` detects audio via ID3 / fLaC / OggS magic prefixes, WAV
  via RIFF/WAVE shape, MP3 via sync-frame, and promotes M4A / M4B
  ftyp-brands off the video path.
- `mutagen>=1.47` added as a required runtime dependency. Deliberation
  documented in `pyproject.toml`: mutagen is pure-Python, ~300 KB, and
  the canonical Python audio-metadata parser; AudioAnalyzer retains
  stdlib fallbacks for WAV / FLAC so coverage does not collapse if
  mutagen is ever swapped out.
- `AudioAnalyzer` exported from `bayyinah.__all__`; registered in
  `default_registry()`; disjoint from every pre-Phase-24 analyzer.

**Phase 25+, CrossModalCorrelationEngine (session 1).** Al-Baqarah
2:164, *"signs for a people who use reason."* No single stem reveals
the full picture; the signs appear when the separated elements are
read together. The engine consumes already-scanned `IntegrityReport`
objects and emits findings for cross-stem divergence that single-stem
analysis misses. It does not reparse files, does not duplicate
detection logic, does not mutate its input, and is idempotent.

- 2 new active mechanisms: `cross_stem_inventory` (always-on meta-
  finding that makes the parting visible; severity 0.00) and
  `cross_stem_undeclared_text` (fires when a subtitle or audio-lyric
  stem carries substantive findings AND the metadata stem is silent
  or its findings do not declare textual content via a narrow keyword
  check, caption / subtitle / lyric / transcript / dialog / narration
  / sdh / cc).
- 5 mechanisms reserved as future work (name-committed in `config.py`
  comments): `cross_stem_text_inconsistency`, `cross_stem_metadata_clash`,
  `embedded_media_recursive_scan`, `cross_stem_coordinated_concealment`,
  `cross_file_media_divergence`.
- 2 paired correlation fixtures (`correlation_aligned.mp4`, subtitle
  and metadata both active, metadata declares captions; rule stays
  silent, vs `correlation_undeclared.mp4`, subtitle loud, metadata
  silent; rule fires).
- `CrossModalCorrelationEngine` exported from `bayyinah.__all__`.
  **Not** wired into `ScanService.default_registry()` in session 1 ,
  opt-in invocation until the rule set stabilises. Callers explicitly
  run the engine over a scanned report and extend findings as needed.

### Changed

- **Registry growth** (all additive): 89 mechanisms at 1.0 → 108
  mechanisms at 1.1 (+8 video, +9 audio, +2 cross-stem). SEVERITY +
  TIER tables grew in lockstep.
- **Public surface** (additive-only): 54 exported symbols at 1.0 → 57
  at 1.1 (+VideoAnalyzer, +AudioAnalyzer, +CrossModalCorrelationEngine).
  Every v1.0 symbol remains exported; removal would fail CI.
- **Default registry** (additive): 13 analyzers at 1.0 → 15 at 1.1
  (+video, +audio registered at the tail after the FallbackAnalyzer).
- **Test suite** (additive): **1,435 passing tests** (verified 2026-04-24,
  10.07-second full-suite runtime), up from the 1.0 baseline. The
  Phase-0 PDF parity sweep continues to pass byte-identically across
  all 17 fixtures.
- **Dependencies**: `mutagen>=1.47` added. `pymupdf` and `pypdf` retain
  their v1.0 constraints.

### Preserved

- **Reference-module MD5s**. `bayyinah_v0.py` (`87ba2ea4…`) and
  `bayyinah_v0_1.py` (`035aa578…`) remain byte-identical to their 1.0
  bytes. The CI workflow continues to assert both.
- **Parity invariant**. `bayyinah.scan_pdf(f) == bayyinah_v0.scan_pdf(f)`
  for every Phase 0 PDF fixture, same findings, same score, same
  error string, same `scan_incomplete` flag.
- **CLI surface**. `bayyinah scan <file>` unchanged; `--json` / `--summary`
  / `--quiet` / exit-code contract (0 / 1 / 2) unchanged.
- **`scan_pdf` / `scan_file` / `format_text_report` / `plain_language_summary`
  entry points** unchanged in behaviour. The kwarg-compat shim for
  `ScanService.scan(pdf_path=…)` that shipped in 1.0 continues to emit
  its `DeprecationWarning` without changing behaviour.

### Documentation

- README.md: supported-formats table extended for video / audio;
  new cross-modal-correlation section.
- CONTRIBUTING.md: stem-extractor-and-router pattern documented as
  the convention for multi-stem format analyzers.

### Known gaps (reserved work)

The following mechanism names are committed in `config.py` comments so
later sessions can register them without name collision, but no
detector fires them in v1.1:

- `video_cross_stem_divergence`, the Phase 23 divergence detector.
- `audio_cross_stem_divergence`, the Phase 24 counterpart.
- `audio_signal_stem_separation` (neural source separation),
  `audio_deepfake_detection`, `audio_hidden_voice_command`, Phase 24
  future work.
- `cross_stem_text_inconsistency`, `cross_stem_metadata_clash`,
  `embedded_media_recursive_scan`,
  `cross_stem_coordinated_concealment`, `cross_file_media_divergence`
 , Phase 25+ future sessions.

The white paper and thesis paper updates for the v1.1 surface are
deferred to Phase 27.

### Foundational paper

Bayyinah's verdict taxonomy (`sahih`, `mushtabih`, `mukhfi`, `munafiq`,
`mughlaq`) and Tier 1/2/3 epistemic discipline are an input-layer
application of Section 9 of the **Munafiq Protocol** (Arfeen, Claude,
2026; DOI [10.5281/zenodo.19677111](https://doi.org/10.5281/zenodo.19677111)).

## [1.0.0]: 2026-04-23

First stable release. Phase 22, Final Release Packaging. Al-Baqarah
2:286: *"Rabbana la tu'akhidhna in nasina aw akhta'na"*, Our Lord, do
not impose blame upon us if we have forgotten or erred. The release
is the ring closed on the twenty-two-phase Al-Baqarah roadmap: the
scanner now holds one contract for twelve file formats, degrades
gracefully under configured ceilings, and never returns silent-clean
on a file it could not identify.

### Added

- **Release status**: PyPI classifier promoted from
  `Development Status :: 3 - Alpha` to
  `Development Status :: 5 - Production/Stable`.
- **GitHub Actions CI** (`.github/workflows/ci.yml`). Matrix across
  Python 3.10 / 3.11 / 3.12 / 3.13. Every push and PR installs the
  package with dev extras, regenerates the fixture corpus, runs the
  full pytest suite, and executes the PDF byte-identical parity sweep
  against `bayyinah_v0` plus the additive-only public-surface check.
- **`CONTRIBUTING.md`**. Six-step "adding a new format" guide,
  five-step workflow restated, ground rules (additive-only,
  ceilings-in-`ScanLimits`, no silent-clean on `UNKNOWN`, emit
  `scan_limited` rather than raise). The contract future contributors
  work to.
- **README.md**, quick-start examples, 12-format support table with
  per-format mechanisms, `ScanLimits` configuration table with
  defaults, fallback-witness explanation, architecture callout
  refreshed to 1.0.

### Supported formats (twelve)

One contract, `BaseAnalyzer.scan(path) -> IntegrityReport`, applied
uniformly across every format:

- **PDF** (`ZahirTextAnalyzer` + `BatinObjectAnalyzer`), text-layer
  zahir/batin (zero-width, TAG, bidi, homoglyphs, invisible render
  modes, microscopic fonts, white-on-white, overlapping text) +
  object-layer batin (JavaScript, OpenAction, additional actions,
  launch actions, embedded files, FileAttachment annotations,
  incremental updates, metadata anomalies, hidden OCGs, adversarial
  ToUnicode CMap).
- **DOCX** (`DocxAnalyzer`), tracked changes, comments, hidden text,
  OLE, external-target relationships.
- **HTML** (`HtmlAnalyzer`), CSS-hidden text, off-screen absolute
  positioning, `<script>` / `on*` handlers, data-URI payloads.
- **XLSX** (`XlsxAnalyzer`), hidden sheets / rows / columns,
  white-on-white cells, formula injection, external links.
- **PPTX** (`PptxAnalyzer`), hidden slides, off-canvas shapes,
  embedded OLE, speaker-notes payloads.
- **EML** (`EmlAnalyzer`), bodyless envelopes, mismatched
  `From` / `Return-Path`, suspicious attachments, nested
  `message/rfc822` recursion.
- **CSV** (`CsvAnalyzer`), formula injection prefixes
  (`=`, `+`, `-`, `@`, tab, CR), Unicode concealment in cells.
- **JSON** (`JsonAnalyzer`), prompt-injection strings, base64 blobs,
  zero-width / TAG characters in values.
- **Markdown / code / plain text** (`TextFileAnalyzer`), zero-width,
  TAG, bidi, homoglyphs, invisible HTML spans.
- **PNG / JPEG / GIF / BMP / TIFF / WebP** (`ImageAnalyzer`), LSB
  steganography, trailing payloads, EXIF anomalies, embedded text
  layers.
- **SVG** (`SvgAnalyzer`), `<script>` tags, `on*` handlers,
  external-ref `<use>`, foreign-object HTML, off-screen text.
- **Unknown** (`FallbackAnalyzer`, Phase 21), universal witness of
  last resort. Every file the router cannot classify surfaces as
  `unknown_format` with forensic metadata (magic-byte prefix,
  extension, size, head preview in hex + ASCII) and
  `scan_incomplete=True`. Closes the silent-clean failure mode.

### Production hardening (Phase 21, carried forward)

- **`ScanLimits`**, single declaration point for every capacity
  ceiling (`max_file_size_bytes`, `max_recursion_depth`,
  `max_csv_rows`, `max_field_length`, `max_eml_attachments`). Frozen
  dataclass; installed per-scan via a thread-local `limits_context`
  so concurrent scans with different limits do not clobber each other.
  Ceiling `0` opts out.
- **`scan_limited` finding** (tier 3, severity 0.0, non-deducting).
  Every analyzer that hits a ceiling emits one, sets
  `scan_incomplete=True`, and returns whatever findings it already
  gathered, graceful degradation under adversarial sizing.

### Preserved (Additive-Only Invariant)

`bayyinah_v0.py` and `bayyinah_v0_1.py` remain byte-identical to their
0.1.0 releases. Every public symbol introduced in the 0.2.x / 0.3.x
refactor series is append-only, no rename, no removal. PDF parity
against `bayyinah_v0` is byte-identical across every Phase 0 fixture
(clean, positive_combined, eight text-layer, seven object-layer) and
re-verified on every CI run.

### Tested against

1283 pytest cases across domain, infrastructure, analyzer, application,
fixture, and end-to-end integration suites. Byte-identical PDF parity
holds on 17 / 17 Phase 0 fixtures. Every adversarial fixture (PDF,
DOCX, HTML, XLSX, PPTX, EML, CSV, JSON, text, image, SVG) asserts its
exact declared mechanism set.

## [0.3.0]: 2026-04-22

Phase 21, Production Hardening. Al-Baqarah 2:286: *"Allah does not burden
a soul beyond its capacity."* The scanner must not burden itself beyond
its configured capacity.

### Added

- **Universal Fallback Analyzer** (`analyzers/fallback_analyzer.py`). Any
  file the `FileRouter` leaves unclassified as `FileKind.UNKNOWN` now
  surfaces one `unknown_format` finding (tier 3, non-deducting) carrying
  forensic metadata: declared extension, file size, magic-byte prefix
  (first 16 bytes, hex-encoded), head-preview in both hex and
  printable-ASCII (first 512 bytes). Scan is marked `scan_incomplete=True`
  so the 0.5 `SCAN_INCOMPLETE_CLAMP` applies. Closes the silent-clean
  failure mode: a file we could not identify no longer slips through as
  score 1.0 with zero findings. Al-Baqarah 2:143 applied to format
  classification.
- **Configurable safety limits** (`domain/config.py`, `ScanLimits`,
  `DEFAULT_LIMITS`, `limits_context`, `get_current_limits`,
  `set_current_limits`). Five frozen-dataclass ceilings declared once:
  - `max_file_size_bytes` (default 256 MB), `ScanService` pre-flight
    before any analyzer runs. Oversize files short-circuit with a single
    `scan_limited` finding.
  - `max_recursion_depth` (default 5), `EmlAnalyzer` nested-message
    recursion. Supersedes the prior hard-coded 3.
  - `max_csv_rows` (default 200 000), `CsvAnalyzer` row walk.
  - `max_field_length` (default 4 MiB), `CsvAnalyzer` per-cell Unicode
    concealment cut-off.
  - `max_eml_attachments` (default 64), `EmlAnalyzer` per-message cap.
  Limits flow into analyzers via a thread-local context manager so the
  `BaseAnalyzer.scan(pdf_path) -> IntegrityReport` contract is unchanged.
  Every analyzer that hits a ceiling emits a `scan_limited` finding
  (tier 3, severity 0.0, non-deducting), sets `scan_incomplete=True`, and
  returns whatever findings it already gathered, graceful degradation,
  never crashes.
- **New mechanisms**: `unknown_format`, `scan_limited`. Both are batin,
  tier 3, severity 0.00 (non-deducting; rely on `scan_incomplete` clamp).
- **Public API surface**: `bayyinah.FallbackAnalyzer`,
  `bayyinah.ScanLimits`, `bayyinah.DEFAULT_LIMITS`,
  `bayyinah.limits_context`, `bayyinah.get_current_limits`,
  `bayyinah.set_current_limits`, `bayyinah.default_registry`.
- **`ScanService(limits=ScanLimits(...))`**, per-service limit override.
  The limits are scoped to the duration of each `scan()` call via
  `limits_context`, so concurrent scans with different limits do not
  clobber each other.

### Preserved (Additive-Only Invariant)

- `bayyinah_v0.py` and `bayyinah_v0_1.py` unchanged. PDF parity
  byte-identical across every Phase 0 fixture. `FallbackAnalyzer` never
  fires on an identified format (`supported_kinds = {FileKind.UNKNOWN}`),
  and the per-format analyzers never see the `scan_limited` mechanism
  unless a caller explicitly tightens `ScanLimits` past the default.

## [0.2.0]: 2026-04-22

### Added

- **Public Python API** (`bayyinah/__init__.py`). `from bayyinah import
  scan_pdf` is now the canonical entry point. Re-exports the orchestrator,
  analyzers, formatters, and domain types.
- **CLI** (`cli/main.py`) with subcommand surface:
  `bayyinah scan <file> [--json | --summary | --quiet]`. Exit codes
  preserved byte-for-byte from v0/v0.1 (0 / 1 / 2 for clean / findings /
  error). `bayyinah --version` added.
- **Domain layer** (`domain/`). Pure data types and scoring primitives ,
  `Finding`, `IntegrityReport`, `compute_muwazana_score`, `tamyiz_verdict`,
  `apply_scan_incomplete_clamp`, `BayyinahError` hierarchy. No I/O, no
  parser dependencies.
- **Infrastructure layer** (`infrastructure/`). `PDFClient` wraps the
  pymupdf + pypdf handles with context-manager safety. `FileRouter`
  detects PDF / DOCX / HTML / JSON / image / code by magic bytes and
  extension, flags polyglot files. `TerminalReportFormatter`,
  `JsonReportFormatter`, `PlainLanguageFormatter`, all byte-identical to
  v0.1's inline `format_text_report` / `plain_language_summary`.
- **Analyzer layer** (`analyzers/`). `BaseAnalyzer` contract enforces a
  uniform per-analyzer `IntegrityReport` shape. `ZahirTextAnalyzer` and
  `BatinObjectAnalyzer` port every detection mechanism from v0.1.
  `AnalyzerRegistry` composes registered analyzers into one merged report
  with the `scan_incomplete` clamp applied post-merge.
- **Application layer** (`application/`). `ScanService` orchestrator:
  file-exists short-circuit → pymupdf preflight → dispatch to the
  registry. Byte-identical behaviour to `bayyinah_v0_1.scan_pdf` across
  every Phase 0 fixture.
- **Test corpus**. 500+ pytest cases across domain, infrastructure,
  analyzers, application, and integration suites. Every Phase 0 fixture
  is asserted for exact mechanism firings, score, error text, and
  scan_incomplete flag against both v0 and v0.1.

### Changed

- `[project.scripts] bayyinah` now points to `cli.main:main` (was
  `bayyinah_v0_1:main`). The `bayyinah_v0` and `bayyinah_v0_1` module-level
  `main` functions remain callable for downstream pins.

### Preserved (Additive-Only Invariant)

- `bayyinah_v0.py` and `bayyinah_v0_1.py` are unchanged. Both remain in
  the wheel as reference implementations. No line was added, removed, or
  modified in either file during the 0.2.0 refactor. Module mtimes
  verified after each phase.

### Architectural References

- [Munafiq Protocol, Detecting Performed Alignment in Artificial
  Systems](https://doi.org/10.5281/zenodo.19677111) (DOI:
  10.5281/zenodo.19677111). The scanner's scoring model (APS-continuous,
  three validity tiers, tamyiz verdict) is a direct port of §9's
  input-layer framing from LLMs to files.
- Internal roadmap: `NAMING.md` captures the Al-Baqarah phase mapping.

## [0.1.0]: 2026-04-22

### Added

- `bayyinah_v0.py`, the original monolithic scanner. Detects:
  - Text-layer mechanisms: `zero_width_chars`, `tag_chars`, `bidi_control`,
    `homoglyph`, `invisible_render_mode`, `microscopic_font`,
    `white_on_white_text`, `overlapping_text`.
  - Object-layer mechanisms: `javascript`, `openaction`,
    `additional_actions`, `launch_action`, `embedded_file`,
    `file_attachment_annot`, `incremental_update`, `metadata_anomaly`,
    `hidden_ocg`, `tounicode_anomaly`.
- `bayyinah_v0_1.py`, fat-split intermediate introducing `PDFContext`,
  `BaseAnalyzer`, `TextLayerAnalyzer`, `ObjectLayerAnalyzer`,
  `ScanService`. Byte-identical output to v0 across the fixture corpus.
- Phase 0 fixture corpus (`tests/fixtures/`): `clean.pdf`,
  `positive_combined.pdf`, 8 text-layer fixtures, 7 object-layer fixtures.
  Each fires exactly its declared mechanism set under v0.

---

**License:** Apache-2.0. See `LICENSE` for the full text. Anthropic's
usage-policies apply when running Bayyinah as an agent tool; see
project README.
