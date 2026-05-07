# Round-by-round failure-mode retirement ledger

Per Bayyinah Audit Framework v3.0 §17.3, the retirement ledger is
the framework's most consequential empirical claim: each retired
shape is one fewer way the substrate can fail, and the retirement
is mechanically prevented by automated gates rather than by author
vigilance.

This document is the cross-version ledger for the Bayyinah
Integrity Scanner. Per-version retirement entries also live in
CHANGELOG.md under the corresponding release section; this ledger
is the consolidated view.

Reconstruction note: rounds 1 through 10 were not numbered
explicitly in early CHANGELOG entries. The numbering below is
reconstructed from CHANGELOG history and from the v1.2.3 audit
work where Fraz Ashraf reviewed the v1.2.2 substrate (recorded as
"round 10" in the v1.2.3 commit messages d032553, e572091,
54942b0, 86c8351). Per the v1.2.4 attribution-discipline note,
all rounds in the Bayyinah chain are audit-of-self by Bilal Syed
Arfeen; Fraz contributed the engineering approach to the audit
framework itself, not to any specific Bayyinah round.

## Ledger

### Round 1 (reconstructed from CHANGELOG, retired in v0.2.x)

- Phase 0 fixture mismatch: hand-rolled fixtures drifted from the
  v0 reference scanner. Closed by adopting `make_test_documents.py`
  and asserting `bayyinah.scan_pdf == bayyinah_v0.scan_pdf`
  byte-identically in the Phase 0 fixture corpus. Structural
  defense: `tests/test_fixtures.py::test_v0_v01_parity`.

### Round 2 (reconstructed from CHANGELOG, retired in v0.3.x)

- Modular surface drift from v0.1: `bayyinah.scan_pdf` stopped
  matching `bayyinah_v0_1.scan_pdf` after analyzer factoring.
  Closed by tightening the parity test to compare finding tuples
  including tier, confidence, description, location, surface,
  concealed. Structural defense:
  `tests/test_integration.py::test_scan_pdf_parity_with_v01`.

### Rounds 3 through 9 (reconstructed from CHANGELOG, retired
across v0.3 through v1.2.2)

- Phase 1-9 modular refactor with byte-parity gates and analyzer-
  per-mechanism factoring. Mechanism registry consistency,
  cost-class taxonomy, content-index pre-pass, mode=production
  early termination, demo firewall, summarisation queue. Each
  phase added a structural defense without breaking parity.

### Round 10 (audit-of-self by Bilal, retired in v1.2.3)

- MEDIUM: requirements-dev.txt out of sync with `pyproject.toml`
  `[project.optional-dependencies].dev`. Closed by adding
  `tests/test_requirements_dev_sync.py` (commit d032553).
- MEDIUM: `SummaryQueue.claim_next_job` returned a stale
  `sqlite3.Row` snapshot; the persisted row was correct, the
  returned dict was lying. Closed by refreshing the returned dict
  to reflect the UPDATE (commit e572091).
- MEDIUM: `tests/test_public_surface_additive.py` pinned only
  `V1_2_0_SURFACE`; framework v3 §18.3 requires per-minor-and-patch
  cadence. Closed by adding `V1_2_1_SURFACE`, `V1_2_2_SURFACE`,
  `V1_2_3_SURFACE` aliases plus subset tests (commit 54942b0).

### Round 11 (audit-of-self by Bilal, queued for v1.2.5)

The red-team probe of bayyinah.dev v1.2.3 on 2026-05-04 surfaced
4 CRITICAL silent-pass findings and 5 HIGH partial-catches against
multi-layer integrity traps. Round 11 is deferred to v1.2.5 per
the v3 depth-before-scope discipline; the Round 12 calibration
corrective ships first because the Round 12 false positives were
visible to every demo visitor while the Round 11 silent-passes
were not.

### Round 12 (audit-of-self by Bilal, retired in v1.2.4)

- HIGH: openaction heuristic fired on benign navigation
  destinations (LibreOffice destination arrays, pdfTeX hyperref
  /GoTo). Closed by adding `_is_benign_navigation_openaction`
  predicate in `analyzers/object_analyzer.py` per ISO 32000-1
  section 12.6.3 (commit 37a466f).
- HIGH: tounicode_anomaly heuristic fired on canonical TeX-stack
  ToUnicode CMaps (Greek-block targets in math fonts, OT1 ZWNJ at
  slot 0x17). Closed by adding `_is_tex_stack_producer` and
  `_is_tex_canonical_anomaly` helpers and threading /Info /Producer
  through both emission paths in `_scan_tounicode_cmaps` (commit
  87cad53).
- MEDIUM: corpus blind spot. Existing fixtures were pymupdf-
  produced and shared library lineage with the analyzer. Closed
  by adding the Round 12 corpus with pdfTeX, LibreOffice, and
  LibreOffice-with-OpenAction fixtures (commit c65e93e), plus a
  structural producer-family coverage test (commit d98edf9).
- Framework recursion: the v3.0 framework PDF (LibreOffice-rendered
  from the docx) returns sahih on both v1.2.3 and v1.2.4. The
  anticipated v3 §9.7 Cross-Document Accounting Drift instance did
  not materialise for this artifact. A regression-pin test is in
  place to detect future drift (commit pending §5).
- DEFERRED to v1.3.0: tounicode_anomaly tier 1 -> tier 2 calibration.
  The tier change is a parity break per `PARITY.md` (the parity
  tuple includes tier); PARITY.md item 5 requires a minor bump for
  any parity break. The locked Round 12 prompt targeted v1.2.4
  patch; the tier downgrade has been deferred to v1.3.0 with the
  proper PARITY.md procedure (issue tag, fixture update, test
  update, minor bump, CHANGELOG Parity-break heading).

## Mechanically prevented from this version forward

The structural defenses that close each ledger entry are
themselves preserved in the codebase and run on CI:

- Byte-parity baseline against v0 / v01 references (since v0.2.x).
- Per-version public surface frozenset cadence (since v1.2.3).
- requirements-dev.txt vs pyproject.toml sync (since v1.2.3).
- openaction destination-vs-action filter (since v1.2.4).
- tounicode_anomaly TeX-stack producer suppression (since v1.2.4).
- Producer-family corpus coverage (since v1.2.4).
- v3.0 framework PDF self-scan regression pin (since v1.2.4).
