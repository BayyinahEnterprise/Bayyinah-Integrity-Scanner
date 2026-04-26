# Furqan Correspondence — Bayyinah Convention → Furqan Primitive

*Bismillah ar-Rahman ar-Raheem.*

The Furqan thesis (Ashraf, Arfeen, et al., 2026) proposes a
programming language whose seven primitives + `scan_incomplete` return
type + Fatiha session protocol formalize the structural-honesty
conventions observed in Bayyinah's development. Section 8.1 of the
Furqan paper makes this claim in summary; this document makes it
**auditable** by naming, for each Furqan primitive, the specific
Bayyinah file, mechanism, test, or workflow that validates it.

If a Furqan primitive cannot be traced to a concrete Bayyinah artifact,
the empirical-foundation claim is weaker than asserted. The table
below ensures every primitive maps to a verifiable element of this
repository.

> **Primitive verification status (v1.1.0):** all nine map to at
> least one auditable artifact in this repository. None is
> aspirational.

---

## Primitive 1 — `bismillah` (scope blocks)

**Furqan claim.** Every module declares `authority`, `serves`,
`scope`, and `not_scope`. Code outside the declared scope is a
compiler error.

**Bayyinah validation.**

| Aspect | Where it lives in this repo |
|---|---|
| Authority declarations | `NAMING.md` (the absolute authority on naming) — referenced as `authority` in every phase prompt |
| Serves clause (purpose hierarchy) | The hierarchy is declared in every phase's Step 1 prompt and surfaced in CONTRIBUTING.md |
| Scope declarations | Each phase prompt opens with explicit `scope` and `not_scope` (see e.g. `history/README.md`, the Phase-23 / 24 / 25+ entries) |
| `not_scope` enforcement at the analyzer level | `BaseAnalyzer.supported_kinds: ClassVar[frozenset[FileKind]]` — every analyzer declares the FileKinds it operates on; the registry refuses to dispatch outside that set |
| Not-scope refusal at the route level | `infrastructure/file_router.py`: extension-fallback for unrecognized magics emits `extension_mismatch=True` rather than letting the file pass into the wrong analyzer |
| Reserved-future-work names | `domain/config.py` comments reserve mechanism names without registering them — the closest live analogue of Furqan's `not_scope` declaration |

The phase prompts in this program literally read like Furqan
`bismillah` blocks. The "authority source / optimization function /
scope / out of scope" structure is in every prompt.

---

## Primitive 2 — `zahir` and `batin` types (surface/depth verification)

**Furqan claim.** Compound types declare a `zahir` (surface
representation) and a `batin` (depth representation). Cross-layer
access without `verify()` is a type error.

**Bayyinah validation.**

| Aspect | Where it lives in this repo |
|---|---|
| The classification itself | `domain/config.py:ZAHIR_MECHANISMS` (frozenset of 27) and `BATIN_MECHANISMS` (frozenset of 81) — every mechanism is in exactly one set |
| Source-layer attribution per finding | `domain/finding.py` and `domain/value_objects.py:SourceLayer = Literal["zahir", "batin"]` — the *type system* assigns each finding to a layer |
| Surface-vs-depth in every analyzer | Each `BaseAnalyzer` subclass declares `source_layer: ClassVar[SourceLayer]` — the analyzer cannot emit findings of the wrong layer |
| Verification at the analyzer level | `analyzers/base.py:_scan_error_report` constructs a finding whose `source_layer` is set from the analyzer's class attribute — the locus is structurally enforced |
| Verification at the cross-modal level | `analyzers/cross_modal_correlation.py:CrossModalCorrelationEngine.correlate(report)` reads `IntegrityReport` findings and emits `cross_stem_undeclared_text` when subtitle/lyric stem (text) and metadata stem (declared surface) disagree — the `verify()` construct in the live system |
| The mechanism-by-mechanism witness | The `bayyinah` and `bayyinah_v0_1` parity check in `tests/test_integration.py` is the surface-depth agreement check across implementations |

This is the strongest correspondence. Bayyinah's entire detection
architecture is the *zahir/batin* distinction made operational at the
file layer.

---

## Primitive 3 — additive-only modules

**Furqan claim.** Exported symbols at version N must exist at
version N+1 with compatible signatures. Removal requires explicit
`major_version_bump`.

**Bayyinah validation.**

| Aspect | Where it lives in this repo |
|---|---|
| Public-surface invariant | `bayyinah/__init__.py:__all__` — 57 symbols at v1.1; the 54 v1.0 symbols are all preserved |
| CI enforcement | `.github/workflows/ci.yml` "Verify additive-only public surface" job — compiles a `required` set of symbols and asserts every one is in `__all__` and bound on the package |
| Reference-module byte-freeze | `.github/workflows/ci.yml` "Verify v0 / v0.1 reference modules unchanged" job — pins MD5 of `bayyinah_v0.py` (`87ba2ea4…`) and `bayyinah_v0_1.py` (`035aa578…`) and asserts on every push |
| Backward-compat shims | `application/scan_service.py:ScanService.scan(file_path=…, *, pdf_path=…)` — the `pdf_path` kwarg shim emits `DeprecationWarning` rather than removing the v1.0 entry point |
| Convention | Documented in `CONTRIBUTING.md` ("additive-only invariant" — every PR must preserve every previously-exported symbol) |

The `additive-only` invariant is not a convention in this
repository — it is **CI-enforced** on every push. That is the
strongest possible form of Furqan's claim that the constraint live in
the type / module system rather than in code review.

---

## Primitive 4 — `mizan` constraints (three-valued calibration)

**Furqan claim.** Optimizations must declare `la_tatghaw` (upper
bound — do not transgress), `la_tukhsiru` (lower bound — do not make
deficient), and `bil_qist` (calibration function). All three must be
satisfied simultaneously.

**Bayyinah validation.**

| Aspect | Where it lives in this repo |
|---|---|
| The scoring primitive | `domain/scoring.py:compute_muwazana_score(findings)` — the function name `muwazana` is itself the Arabic root of `mizan` |
| Score formula | `score = clamp(1.0 - sum(severity * confidence), 0, 1)` — bounded above by 1.0, below by 0.0; the formula itself is a three-valued calibration |
| Tier classification | `domain/config.py:TIER` — every mechanism declares Tier 1 (verified) / Tier 2 (structural) / Tier 3 (interpretive); the tier governs which findings deduct vs which are informational |
| Severity weights with calibration discipline | `domain/config.py:SEVERITY` — per-mechanism floats, calibrated against fixture corpora, never tuned to a single benchmark |
| `scan_incomplete` clamp (the `la_tatghaw`/`la_tukhsiru` interplay) | `domain/scoring.py:apply_scan_incomplete_clamp` — clamps the integrity score to 0.5 when the scan was not exhaustive (do not over-report cleanness; do not under-report when partial evidence exists) |
| FRaZ awareness | `domain/config.py:DEFAULT_LIMITS` — the `ScanLimits` dataclass declares per-scan ceilings; configurable per-call via `limits_context()` |
| CONTRIBUTING.md guidance | "Adding a new mechanism normally requires additions in three places: (1) source-layer classification, (2) APS severity weights, (3) validity tier" — the three-place rule mirrors `mizan`'s three-valued constraint |

---

## Primitive 5 — `tanzil` build ordering (phased compilation)

**Furqan claim.** Modules declare phase numbers. Phase N's full test
suite must pass before Phase N+1 compiles. Regressions in Phase N
block all subsequent phases.

**Bayyinah validation.**

| Aspect | Where it lives in this repo |
|---|---|
| The phased development sequence | 25+ phases through v1.1, each named in the per-phase prompt and committed as a unit with verification before next-phase work begins |
| The verification gate between phases | Every phase's Step-5 (Final Regression) requires the full pytest suite + PDF parity to pass before declaring the phase complete |
| Phase log | `CHANGELOG.md` records Phases 22 (1.0 release packaging) through 25+ (cross-modal correlation session 1) — every entry names what was added, what was preserved, what is reserved future work |
| Cross-phase regression discipline | The CI workflow regenerates the full fixture corpus on every push, then runs the full pytest suite — a regression in any phase blocks the entire CI pipeline |
| No forward references | Each phase's analyzer declares `supported_kinds` that are disjoint from previous phases' `supported_kinds` — the dispatch is structurally ordered |
| The 22-phase canonical record | `bayyinah_v0.py` (Phase 0) and `bayyinah_v0_1.py` (Phase 0.5 fat-split) are byte-frozen with MD5 pins — the literal first phases preserved in their original form |

The numerical evidence the Furqan paper cites: **zero cross-phase
regressions across the full development sequence**, verified by CI on
every push. That is the empirical content of `tanzil`.

---

## Primitive 6 — ring-composition verification

**Furqan claim.** Every module closes with a `ring_close` block
that asserts structural consistency with its opening `bismillah`.

**Bayyinah validation.**

| Aspect | Where it lives in this repo |
|---|---|
| Per-phase ring closure | Every phase prompt opens with Step 1 (Bismillah) and closes with Step 7 (Anti-Pattern Avoidance) + final regression. The closing must match the opening's declared scope. |
| Structural ring closure in code | `BaseAnalyzer.scan(file_path) -> IntegrityReport` — the contract opens with a file path and must close with a well-formed IntegrityReport whose findings all reference registered mechanisms (the ring is the input → registered-output structure) |
| The fixture-walker tests | `tests/test_*_fixtures.py` parametrise on `<format>_FIXTURE_EXPECTATIONS` and assert exact mechanism firing — every fixture's expectation is declared in `make_*_fixtures.py` (the opening); every test asserts against it (the closing) |
| The CrossModalCorrelationEngine | `analyzers/cross_modal_correlation.py:_rule_inventory` always emits `cross_stem_inventory` listing the stems the engine observed — the inventory is the explicit ring-closure for cross-stem analysis |
| Each session's deliverable check | The `## Final scorecard` table in CHANGELOG entries is the ring-closure: opening "Phase N — what we are adding" closes with "what was added + what was preserved + what was deferred" |

---

## Primitive 7 — `marad` error types (diagnosis-structured errors)

**Furqan claim.** Errors carry `diagnosis`, `location`,
`minimal_fix`, and `regression_check` fields. Catching a `marad`
without a regression check is a compiler warning.

**Bayyinah validation.**

| Aspect | Where it lives in this repo |
|---|---|
| `Finding` as a `marad` | `domain/finding.py:Finding` carries `mechanism` (diagnosis label), `location` (where), `description` (what specifically), `surface` + `concealed` (the divergence) — the `marad` shape applied to detection findings |
| `scan_error` mechanism | `domain/config.py:BATIN_MECHANISMS` includes `scan_error` — when an analyzer fails internally, the failure surfaces as a structured `Finding` with diagnostic context, not as a swallowed exception |
| `unknown_format` mechanism | `analyzers/fallback_analyzer.py` — when the FileRouter cannot classify a file, the fallback analyzer emits `unknown_format` with magic-byte prefix, extension, size, and head-preview as forensic diagnosis |
| `scan_limited` mechanism | When a `ScanLimits` ceiling is reached, the analyzer emits `scan_limited` with the specific ceiling that fired — the `minimal_fix` is implicit in the named limit (raise the limit if the file genuinely needs more) |
| Disease-not-betrayal debugging convention | The EML-phase fix recorded in `history/ASSESSMENT_RESPONSE.md` and the recurring "minimal fix + regression check" pattern in CONTRIBUTING.md |
| CONTRIBUTING.md guidance | "Diagnose, do not rewrite" — explicit in the workflow: when a test fails, find the line, name the divergence, write the smallest fix, run the suite |

---

## Primitive 8 — `scan_incomplete` return type

**Furqan claim.** Functions that may not fully process their input
must return a type carrying the incompleteness signal. A function
returning the full type on a partial input is a type error.

**Bayyinah validation.**

| Aspect | Where it lives in this repo |
|---|---|
| The literal field | `domain/integrity_report.py:IntegrityReport.scan_incomplete: bool` — every report carries this flag |
| The clamp | `domain/scoring.py:apply_scan_incomplete_clamp` — when `scan_incomplete=True`, the integrity score is clamped to 0.5 |
| The propagation | `application/scan_service.py:ScanService.scan` — if any analyzer sets `scan_incomplete`, the merged report inherits the flag |
| Per-analyzer incompleteness signalling | Every `BaseAnalyzer` subclass that hits a `ScanLimits` ceiling emits `scan_limited` and sets `scan_incomplete=True` — the analyzer cannot return a clean score on input it could not fully read |
| FallbackAnalyzer | Emits `unknown_format` and sets `scan_incomplete=True` — Furqan's claim made literal: a clean-looking score (1.0) is not allowed on a file we could not classify |

The Furqan paper (Section 4) cites this exact behaviour:
*"Bayyinah's scan_incomplete clamp enforces this at the scanner
level: the scanner never returns a score of 1.0 (clean) on a
document it could not fully read."* The mechanism lives in
`domain/scoring.py` and is asserted by the test suite on every push.

---

## Primitive 9 — Fatiha session protocol

**Furqan claim.** When Furqan is used in human-AI collaborative
development, the seven steps of the Fatiha Construct are IDE-level
prompts that must be completed before the session's first code
change compiles.

**Bayyinah validation.**

| Aspect | Where it lives in this repo |
|---|---|
| Every phase prompt | The phase prompts that produced this codebase open with the seven steps — Step 1 Bismillah, Step 2 Alhamdulillah, Step 3 Ar-Rahman ar-Rahim, Step 4 Maliki Yawm ad-Din, Step 5 Iyyaka Na'budu, Step 6 Ihdina as-Sirat, Step 7 Sirat Alladhina |
| The structure documented | `history/README.md` records the per-generation phase progression; CHANGELOG records the per-phase deliverable; the per-session prompts in conversation history follow the Fatiha structure literally |
| The orientation check (Step 5) | Every phase has an "am I building or performing?" check; the response to Perplexity's "fix the homoglyph fixture" claim was a literal Step-5 invocation: the suite was green, the claim did not match the state, the fix would have been performed productivity |
| The 20% skip rule | Documented in CONTRIBUTING.md and applied repeatedly when a sub-task threatened to consume the session (e.g., the per-phase "Skip rule: register as future work" register pattern) |
| The anti-pattern step (Step 7) | Every phase's Step 7 names specific historical anti-patterns to avoid — visible in conversation history |

The Fatiha Construct is the methodology that **produced** this
codebase. Furqan's claim that the construct could be IDE-enforced is
empirically grounded in the fact that the construct was already
prompt-enforced and produced verifiable output.

---

## Summary verification table

| Furqan Primitive | Validated by Bayyinah element | CI-enforced |
|---|---|---|
| `bismillah` (scope blocks) | `BaseAnalyzer.supported_kinds`, NAMING.md, phase prompts | partial (registry refuses out-of-scope dispatch) |
| `zahir` / `batin` types | `ZAHIR_MECHANISMS`, `BATIN_MECHANISMS`, `SourceLayer`, `BaseAnalyzer.source_layer` | yes (test_finding asserts the inference) |
| Additive-only modules | `bayyinah.__all__`, CI workflow, MD5 pins on v0/v0_1 | **yes** (CI fails if any v1.0 symbol is removed or md5s drift) |
| `mizan` constraints | `compute_muwazana_score`, SEVERITY/TIER tables, ScanLimits, `apply_scan_incomplete_clamp` | yes (test suite asserts score formula) |
| `tanzil` build ordering | 25+ phase sequence, per-phase regression gates, byte-frozen v0/v0_1 | **yes** (CI runs full suite + parity sweep) |
| Ring-composition | Per-phase Step-1↔Step-7 closure, fixture-walker tests, `*_inventory` meta-findings | yes (fixture walker tests assert exact mechanism set) |
| `marad` errors | `Finding` shape, `scan_error` / `unknown_format` / `scan_limited` mechanisms | yes (test suite covers every error path) |
| `scan_incomplete` return type | `IntegrityReport.scan_incomplete`, score clamp to 0.5 | yes (clamp test in test_integrity_report) |
| Fatiha session protocol | Phase prompts, CONTRIBUTING.md workflow, conversation history | partial (prompt-enforced, not yet IDE-enforced) |

---

## Conclusion

Every Furqan primitive maps to at least one auditable Bayyinah artifact.
For the strongest claims (`additive-only modules`, `tanzil build
ordering`, `zahir/batin types`), the validation is CI-enforced on
every push. For the more interpretive primitives (`bismillah` scope,
ring-composition, the Fatiha session protocol), the validation lives
in the prompt-and-convention layer and is enforced by code review
under the COMPLIANT / PARTIAL / BLOCKED governance protocol
(Ashraf, 2026).

Furqan's claim is therefore precise: the language formalizes
behavioural conventions that *already operate correctly* in a
shipped codebase. The compiler the paper proposes would move the
prompt-and-convention enforcement into the type system, eliminating
the dependence on review discipline. But the conventions themselves
are not aspirational — they are how this repository got built and how
it stays correct on every push.

*"Blessed is He who sent down the Furqan upon His servant that he
may be to the worlds a warner."* — Al-Furqan 25:1

The compiler does not yet exist. The conventions do.
