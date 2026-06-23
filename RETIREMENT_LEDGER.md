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

### Round 11 (audit-of-self by Bilal, in-progress at v1.2.5)

The red-team probe of bayyinah.dev v1.2.3 on 2026-05-04 surfaced
4 CRITICAL silent-pass findings and 5 HIGH partial-catches against
multi-layer integrity traps. Round 11 is deferred to v1.2.5 per
the v3 depth-before-scope discipline; the Round 12 calibration
corrective ships first because the Round 12 false positives were
visible to every demo visitor while the Round 11 silent-passes
were not.

v1.2.5 status (2026-06-22, CODING_STRATEGY cycle-1+P+P+R termination
substrate; Fatiha session per CODING_STRATEGY §5 + verse 2:11-12):

- `tests/fixtures/round11/` directory scaffolded with corpus README
  documenting fixture convention and best-judgement trap-class
  hypotheses. Per Iyyaka Na'budu Step 5 orientation check and Cow
  Episode anchor: the actual 4 CRITICAL + 5 HIGH trap classes are not
  enumerated in this ledger or in CHANGELOG.md at v1.2.4; the canonical
  source is the 2026-05-04 red-team probe document held by the
  project-lead.

- F-CS-V125-001 (MEDIUM, audit-of-self): Round 11 trap enumeration not
  in v1.2.4 substrate-of-record. Disposition: scaffold corpus structure
  + RETIREMENT_LEDGER + CHANGELOG entries pending project-lead provision
  of the red-team probe document. Closure mechanism work resumes when
  the document is supplied.

- Best-judgement trap-class hypotheses (NOT canonical) documented in
  `tests/fixtures/round11/README.md`:
  * 4 CRITICAL candidates: pdf_objstm_concealed_text +
    cross_format_payload_pairing + html_inline_event_handler_payload +
    xlsx_worksheet_xml_comment_payload
  * 5 HIGH candidates (tier reclassifications): svg_defs_unreferenced_text
    + csv_payload_in_adjacent_cell + eml_header_continuation_payload +
    json_nested_payload + xlsx_defined_name_payload

- PARITY contract: additive-only per PARITY.md. New mechanisms add to
  MECHANISM_REGISTRY; tier reclassifications go through the parity-break
  ceremony at v1.3.0 if any Phase 0 fixture's to_dict() byte-changes.

- Slip discipline per CODING_STRATEGY §6 v1.2.5 Maliki Yawm ad-Din: if
  the red-team probe document is not supplied within the v1.2.5 dispatch
  budget, the round closures defer to v1.2.6 bridge-tag per release-gate
  slip discipline; the major version target remains v1.3.0 ceremony at
  whatever the post-round-11 substrate state is.

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

### Round 13 (audit-of-self by Bilal, retired in v1.3.0)

- HIGH: tounicode_anomaly tier 1 -> 2 reclassification. The mechanism
  was filed at tier 1 (high-confidence concealment) before Round 12's
  calibration evidence established that legitimate TeX-stack ToUnicode
  CMaps (OT1/T1 fonts, Greek/math glyph targets, pdfTeX hyperref,
  LibreOffice destination arrays, ZWNJ at slot 0x17) produce shapes
  the heuristic correctly classifies as anomalous without concealment
  intent. Tier 2 (structural pattern with intent-ambiguity) is the
  substrate-honest classification. The single-line tier change in
  `domain/config.py` is the entire mechanism modification; the
  analyzer detection logic is unchanged.

The parity-break ceremony per PARITY.md procedure: (1) issue tagged
parity-break with calibration-evidence cross-reference; (2) CHANGELOG
v1.3.0 entry under `Parity-break` heading; (3) Phase 0 fixture
expected outputs admit the tier=1 -> tier=2 divergence via the
`_v1_3_0_tounicode_tier_remap` function in `tests/test_integration.py`;
(4) `test_scan_pdf_parity_with_v0` + `test_scan_pdf_parity_with_v01`
updated to apply the remapper; (5) minor version bumped 1.2.4 ->
1.3.0.

The v0 + v0_1 reference scanners are UNCHANGED. They continue
emitting tier=1 for tounicode_anomaly per their frozen reference
behavior. The modular `bayyinah.scan_pdf` public API emits tier=2
starting at v1.3.0. The asymmetric parity is admitted in the test
infrastructure via the documented remapper; PARITY.md ledger
records the ceremony.

Q2 (Is the parity-with-v0 invariant load-bearing or contingent?)
its first data point at Round 13: the invariant is contingent
on v0 correctness; the ceremony exists precisely for this case.
Future parity-breaks accumulate Q2 evidence.

Mechanism count unchanged at 159 (tier value modification is not
mechanism addition or removal). MECHANISM_REGISTRY coherence
assertions pass at v1.3.0 import.

### Round 14 (audit-of-self by Bilal, retired in v1.4.0)

- HIGH: `compute_muwazana_score` shape pinned. Existing continuous-
  and-saturating semantics documented in docs/score.md §1 and pinned
  by regression tests in tests/contracts/test_muwazana_score_shape.py.
  No redesign; no behavior change. The shape is byte-identical to
  bayyinah_v0.compute_integrity_score. Q3 (score function collapses
  heterogeneous risk) closure-log data point #1 filed.

- HIGH: `apply_scan_incomplete_clamp` semantics pinned. Existing
  `SCAN_INCOMPLETE_CLAMP = 0.5` clamp value documented in docs/score.md
  §2 with truth-table and pinned by regression tests in tests/
  contracts/test_scan_incomplete_clamp.py. No redesign; no behavior
  change. The semantics are byte-identical to bayyinah_v0_1 inline
  clamp logic. Q4 (`0.5` clamp lives inside continuous distribution)
  closure-log data point #1 filed.

- MEDIUM: `tamyiz_verdict` decision-table pinned per docs/score.md §3.
  No code change; the existing rule-order (Tier 0 routing -> scan_
  incomplete -> sahih -> munafiq -> mukhfi -> mushtabih) is documented
  canonically for the first time. Future modifications require parity-
  break ceremony per PARITY.md.

The release is documentation + regression-test additions. No analyzer
modifications, no MECHANISM_REGISTRY changes, no tier reclassifications.
The patent invariant clause (CODING_STRATEGY §7: analyzer registry 130,
layer-classification 132/136, producer-signature calibration 134,
verdict aggregator 150 with five-verdict structure, witness emitter 160)
is preserved unchanged.

PARITY contract holds: byte-identity between v0/v0_1/current scan
output is preserved at v1.4.0 (no score function modification; no
clamp modification). The v1.3.0 tounicode_anomaly tier remapper from
tests/test_integration.py continues to apply per its v1.3.0 ledger
entry; no new remappers added at v1.4.0.

Mechanism count unchanged at 159. MECHANISM_REGISTRY coherence
assertions pass at v1.4.0 import.

### Round 15 (audit-of-self by Bilal, retired in v1.5.0)

- MEDIUM: KNOWN_LIMITS.md authored at repo root (216 lines) per QUESTIONS.md
  Q1 closure target and CODING_STRATEGY §6 v1.5.0 Fatiha session (al-Baqarah
  2:32 verse anchor). The document enumerates 9 limitation classes empirically
  grounded in existing CHANGELOG / QUESTIONS / RETIREMENT_LEDGER references;
  no hypothetical limitations per Cow Episode anchor.

- LOW: docs/principles.md stub authored (52 lines, structure only). Full
  framework-free engineering principles content is the v1.9.0 deliverable
  per CODING_STRATEGY §6 v1.9.0 + QUESTIONS.md Q10 closure target.

The release is documentation-only. No analyzer modifications, no
MECHANISM_REGISTRY changes, no tier reclassifications, no test
modifications. Per CODING_STRATEGY §6 v1.5.0 audit-intensity LIGHT
default + Cow Episode anchor: empirical gaps only; no padding.

PARITY contract holds unchanged. The v1.3.0 tounicode_anomaly tier
remapper in tests/test_integration.py + tests/analyzers/test_object_
analyzer.py + tests/application/test_scan_service.py continues to apply
per its v1.3.0 PARITY.md ledger entry; no new remappers added at v1.5.0.

Mechanism count unchanged at 159. MECHANISM_REGISTRY coherence
assertions pass at v1.5.0 import. bayyinah.__version__ bumped 1.4.0
-> 1.5.0 to match pyproject.toml (per TestReleaseReadiness
test_pyproject_version_matches_package_version invariant).

### Round 16 (audit-of-self by Bilal, retired in v1.6.0)

- MEDIUM: silent-skip risk class for any budget controller bolted onto
  the scan path. Bayyinah ships at v1.6.0 with a pure projection layer
  at `application/budget_controller.py` (203 lines) that partitions
  MECHANISM_REGISTRY against a cost ceiling and surfaces
  `scan_incomplete_implied` whenever truncation would occur. The
  Verse 2:188 honest-accounting reading is structurally enforced by
  the `BudgetPlan.__post_init__` invariant + four contract tests at
  `tests/contracts/test_budget_controller.py::TestHonestScanIncomplete`.
  Per Q-PRO-3 closure (`docs/budget.md`).

- MEDIUM: supply-chain scope drift risk. Without explicit disposition,
  a content scanner could accumulate provenance-verification analyzers
  (SBOM ingestion, in-toto attestation reading, Sigstore signature
  consumption) and quietly subsume a separate threat model. Closed by
  authoring `docs/supply_chain_disposition.md` (139 lines) declaring
  supply-chain detection OUT OF SCOPE for v1.x and v2.x with a three-
  part rationale (different witnesses, mature external ecosystem,
  patent-surface boundary). Composition deferred to v3.0+ enterprise
  tier per ROADMAP_TO_V5.md. Per Q-PRO-4 closure
  (`docs/supply_chain_disposition.md`).

- LOW: cost-class enumeration drift risk. The taxonomy at
  `domain/cost_classes.py` is the authoritative source for cost classes
  A through D. v1.6.0 does NOT add a new cost class; the budget
  controller consumes the frozen taxonomy as-is. Structural defense:
  `tests/contracts/test_budget_controller.py::TestPureProjection`
  pins that `plan_scan_budget` does not mutate
  `MECHANISM_REGISTRY` or `MECHANISM_COST_CLASS`.

The release is additive. No analyzer modifications, no MECHANISM_REGISTRY
changes, no tier reclassifications, no test modifications to existing
test files. Per CODING_STRATEGY §6 v1.6.0 audit-intensity STANDARD +
Cow Episode anchor: smallest honest contribution; no scope drift into
ScanService.scan() signature changes or supply-chain detectors.

PARITY contract holds unchanged. The v1.3.0 tounicode_anomaly tier
remapper in tests/test_integration.py + tests/analyzers/test_object_
analyzer.py + tests/application/test_scan_service.py continues to apply
per its v1.3.0 PARITY.md ledger entry; no new remappers added at v1.6.0.

Mechanism count unchanged at 159. MECHANISM_REGISTRY coherence
assertions pass at v1.6.0 import. bayyinah.__version__ bumped 1.5.0
-> 1.6.0 to match pyproject.toml (per TestReleaseReadiness
test_pyproject_version_matches_package_version invariant).

### Round 17 (audit-of-self by Bilal, retired in v1.7.0)

- MEDIUM: silent-default-flip risk class for the Phase 25+
  `CrossModalCorrelationEngine`. A future release that wires the
  engine into `ScanService.scan()` or `ScanService.scan_batch()`
  without invoking the PARITY-break ceremony would change finding
  counts on every multi-modal fixture (each gains at least one
  `cross_stem_inventory` finding) and silently shift downstream-
  consumer expectations. Closed by authoring `docs/cross_modal.md`
  (188 lines) declaring the substrate-actual policy: Phase 12
  default-on, Phase 25+ opt-in. Structural defense:
  `tests/contracts/test_cross_modal_policy.py::TestPhase12DefaultOn`
  + `TestPhase25PlusDefaultOff` (8 test functions) pin the policy.
  A legitimate future flip must remove these tests as part of the
  PARITY-break ceremony, making the change visible in the diff.

- LOW: Q5 disambiguation risk class. The original Q5 question
  framing in QUESTIONS.md treated "cross-modal correlation" as a
  single opt-in surface; the substrate actually ships two surfaces
  (Phase 12 and Phase 25+) with different policies. Closed by the
  Q5 closure-log data point #1 disambiguating which engine the
  question refers to and documenting both surfaces in
  `docs/cross_modal.md` §1.

- LOW: future-work rule name accountability. Five rule names
  reserved in `domain/config.py` comments
  (`cross_stem_text_inconsistency`, `cross_stem_metadata_clash`,
  `embedded_media_recursive_scan`, `cross_stem_coordinated_concealment`,
  `cross_file_media_divergence`) have been on the books since
  Phase 25+ session 1. The v1.7.0 closure documents these as the
  conditions for a default-on flip in `docs/cross_modal.md` §5,
  binding future work to either shipping the detectors or closing
  the names explicitly before the default flips.

The release is additive. No analyzer modifications, no
MECHANISM_REGISTRY changes, no ScanService.scan() / scan_batch()
behavior changes, no tier reclassifications. Per CODING_STRATEGY
§6 v1.7.0 audit-intensity STANDARD + Cow Episode anchor: documents
existing substrate, pins boundary, defers PARITY-break to a future
dedicated round.

PARITY contract holds unchanged. The v1.3.0 tounicode_anomaly tier
remapper continues to apply per its v1.3.0 PARITY.md ledger entry;
no new remappers added at v1.7.0.

Mechanism count unchanged at 159. MECHANISM_REGISTRY coherence
assertions pass at v1.7.0 import. bayyinah.__version__ bumped 1.6.0
-> 1.7.0 to match pyproject.toml (per TestReleaseReadiness
test_pyproject_version_matches_package_version invariant).

### Round 18 (audit-of-self by Bilal, retired in v1.8.0)

- HIGH: single-witness blind-spot risk class. A test suite that
  witnesses only itself can pass while the analyzer it tests is
  silently broken. The README invokes the two-witnesses principle
  (al-Baqarah 2:282) but Bayyinah was the only witness to its own
  output through v1.7.0. Closed by shipping the
  `DifferentialWitness` ABC at `tests/differential/witness_contract.py`
  + Priority 1 pdfid external witness at
  `tests/differential/test_pdfid_witness.py` per Q8 closure
  (`docs/differential_testing.md` §3.1).

- MEDIUM: score-function property-space gap. Existing
  fixture-pinning tests sampled the score function at finite
  fixture-defined points. Five continuous-domain invariants (range,
  empty-list, idempotence, monotonicity in finding count, saturation
  at zero) were not pinned over the strategy space. Closed by
  `tests/contracts/test_score_properties.py` Hypothesis-based
  property pins per `docs/differential_testing.md` §4. Plus order
  invariance pinned as a consequence of sum-commutativity.

- LOW: witness-skip silent-pass risk class. An external witness that
  silently passes when its tool is unavailable would defeat the
  two-witnesses thesis. Closed by `DifferentialWitness` contract
  documented in `docs/differential_testing.md` §2.3: witnesses
  return [] when unavailable (never raise) and tests use
  `@pytest.mark.skipif` with documented install hints. Structural
  defense: `tests/differential/test_pdfid_witness.py::TestPdfIdWitnessContract`
  pins both behaviors.

- LOW: optional-dependency dilution risk class. Hypothesis and pdfid
  are added to `[project.optional-dependencies] dev` at v1.8.0, not
  to runtime dependencies. Runtime install footprint is unchanged.
  Structural defense: pyproject.toml `dev` extra carries both with
  major-version caps (`hypothesis>=6,<7`, `pdfid>=1.1,<2`) per
  dependency manifest discipline.

The release is additive. No analyzer modifications, no
MECHANISM_REGISTRY changes, no ScanService.scan() / scan_batch()
behavior changes, no tier reclassifications, no score-function
semantic changes. Per CODING_STRATEGY §6 v1.8.0 audit-intensity
HEAVY + Cow Episode anchor: ship Priority 1 witness + property
pins + architecture; defer Priorities 2-4 + mutation + fuzz.

PARITY contract holds unchanged. The v1.3.0 tounicode_anomaly tier
remapper continues to apply per its v1.3.0 PARITY.md ledger entry;
no new remappers added at v1.8.0.

Mechanism count unchanged at 159. MECHANISM_REGISTRY coherence
assertions pass at v1.8.0 import. bayyinah.__version__ bumped 1.7.0
-> 1.8.0 to match pyproject.toml (per TestReleaseReadiness
test_pyproject_version_matches_package_version invariant).

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
- BudgetPlan honest-accounting invariant: __post_init__ enforces that
  `scan_incomplete_implied` cannot be False whenever `out_of_budget`
  is non-empty (since v1.6.0).
- BudgetPlan partition-coverage invariant: __post_init__ enforces that
  `in_budget | out_of_budget == MECHANISM_REGISTRY` exactly (since
  v1.6.0).
- Cross-modal policy default-on/default-off pin: ScanService default
  has Phase 12 CorrelationEngine attached and explicitly NOT a Phase
  25+ CrossModalCorrelationEngine (since v1.7.0).
- Phase 25+ post-processor isolation: CrossModalCorrelationEngine is
  NOT a BaseAnalyzer subclass, blocking AnalyzerRegistry from
  dispatching it as a side effect of a scan (since v1.7.0).
- Score-function property pins: range [0,1], empty-list -> 1.0,
  idempotence, monotonicity in finding count, saturation at zero,
  order invariance enforced over the Hypothesis strategy space
  (since v1.8.0).
- DifferentialWitness contract: `WitnessDivergence.__post_init__`
  enforces the three-kind partition (solo_bayyinah / solo_witness /
  distinct_locus); witnesses must return [] not raise; witnesses
  must declare an install hint (since v1.8.0).
