# Open Questions

A live list of interpretive questions about Bayyinah's own design that the project has not yet resolved. Publishing it is the recursive application of the project's thesis: a tool that detects performed alignment in other artifacts has to surface the gap between its own surface claims and its own substrate, or the tool is itself performing alignment.

This file is appended to, not rewritten. Questions move to a "Resolved" section with the version that resolved them. Questions are not bugs -- they are interpretive issues whose right answer is not yet obvious.

## Maintainer

Bilal Syed Arfeen, project lead.

## Acknowledgement

This file was prompted by an external audit from Fraz Ashraf in May 2026. Several of the open questions below restate findings from that audit verbatim. The audit applied Bayyinah's own thesis to Bayyinah and found gaps the project had not surfaced internally; the appropriate response is to surface them publicly rather than absorb them silently.

## Open

### Q1. What is the adversarial document the score function cannot detect?

The integrity score is `clamp(1.0 - sum(severity * confidence), 0, 1)`. The score function is monotonic in finding count and severity but does not encode coverage. The honest claim is that the score is meaningful only when no concealment shape escaped the analyzer pipeline. Q1 is to construct, document, and publish in `KNOWN_LIMITS.md` a single adversarial document that scores 1.0 on the default pipeline despite carrying concealed payload, with the construction method.

This is the project's strongest possible affirmation of its own thesis. A scanner that publishes the shape of the input it cannot see is harder to attack than one that claims completeness.

**v1.5.0 closure-log data point #1 (Round 15, 2026-06-22):** KNOWN_LIMITS.md
authored at repo root (216 lines) declaring the score-function blind spot
general form publicly per CODING_STRATEGY §6 v1.5.0 (al-Baqarah 2:32 verse
anchor: "we have no knowledge except what You have taught us"). The Q1
thesis-affirmation closure: a scanner that publishes the shape of the input
it cannot see is harder to attack than one that claims completeness.

The Q1 declaration scope at v1.5.0: BLIND-SPOT GENERAL FORM is published in
KNOWN_LIMITS.md §1; the construction of a specific adversarial fixture
demonstrating `score == 1.0` on a concealed-payload document is queued for
later releases (v1.6.0 -- v1.8.0) as the substrate matures. The honest
publication of the blind spot IS the v1.5.0 Q1 closure per the Q1 thesis;
the empirical fixture follows.

Cross-reference: KNOWN_LIMITS.md §1 + docs/score.md §1 + CODING_STRATEGY §6
v1.5.0 + ROADMAP_TO_V5 §3.0 (audio/video deferred) + ROADMAP_TO_V5 §4.0+
(source-code substrate deferred). Q1 stays in OPEN-with-closure-data-points
status: the construction-method publication is data point #1; the empirical
adversarial fixture, when authored, becomes data point #2.

### Q2. Is the parity-with-v0 invariant load-bearing or contingent?

`bayyinah.scan_pdf == bayyinah_v0.scan_pdf` on every Phase 0 fixture is asserted as a structural-honesty guarantee. It is also a guarantee that every defect in v0 ships forever, because fixing it breaks the invariant. The parity policy is being made conditional in this release (see `PARITY.md`) but the deeper question remains: at what threshold does v0's correctness become more important than reproduction of v0's behavior?

**v1.3.0 closure-log data point #1 (Round 13, 2026-06-22):** the
tounicode_anomaly tier 1 -> 2 reclassification is the first empirical
data point against this question. The parity-break ceremony executed
per `PARITY.md` produces a documented, version-bumped, ledger-recorded
event; the test infrastructure admits the divergence via the
`_v1_3_0_tounicode_tier_remap` remapper in `tests/test_integration.py`.

The discipline answer materialising from this first data point: the
invariant is **contingent on v0 correctness**; the ceremony exists
precisely for this case. The threshold at which v0's correctness
overrides v0's reproduction is the threshold at which calibration
evidence accumulates against the v0 behavior -- which is what Round
12 (v1.2.4) established for tounicode_anomaly. The parity-break
ceremony is the mechanism by which the project converts calibration
evidence into a version-bumped behavior change while preserving v0
+ v0_1 as historical reference scanners.

Q2 accumulates evidence across subsequent parity breaks. v1.3.0 is
data point 1. Q3 (compute_muwazana_score shape) and Q4 (scan_incomplete
clamp semantics) per CODING_STRATEGY §6 v1.4.0 will provide further
data points; both are pinned at v1.4.0 per the Fatiha session sequence.

### Q3. The score function collapses heterogeneous risk

A document with five findings and a document with fifty findings both clamp to 0.0. For triage at scale this loses information; for compliance gates it loses more. Q3 is whether the score should remain continuous-and-saturating (current shape) or split into a continuous score plus a separate finding-count and coverage axis, and what the migration path is for downstream consumers who pin to the current shape.

**v1.4.0 closure-log data point #1 (Round 14, 2026-06-22):** the score
function shape ships at v1.4.0 with continuous-and-saturating shape
PINNED per docs/score.md §1. The decision is NOT to split into score-
and-finding-count axes at this release. Rationale: byte-identity with
bayyinah_v0.compute_integrity_score is preserved; consumers needing
finding-count or per-tier resolution access the findings list directly
on IntegrityReport. Future redesigns proposing a split require the
parity-break ceremony per PARITY.md with calibration evidence.
Cross-reference: docs/score.md §4 (Q3 closure note) +
tests/contracts/test_muwazana_score_shape.py (regression pin).

### Q4. The `0.5` clamp lives inside a continuous distribution

A score of `0.5` in a CI dashboard is ambiguous: half-dirty file, or unscanned? `scan_incomplete=True` exists to disambiguate but the score channel re-introduces the type confusion the flag exists to prevent. v1.2 adds `scan_complete: bool` and a `coverage` field to the report; whether the score itself should be `null` when incomplete (rather than clamped to 0.5) remains open.

**v1.4.0 closure-log data point #1 (Round 14, 2026-06-22):** the clamp
semantics ship at v1.4.0 with `SCAN_INCOMPLETE_CLAMP = 0.5` PINNED per
docs/score.md §2. The decision is NOT to switch to `score=None` for
incomplete scans at this release. Rationale: byte-identity with
bayyinah_v0_1 clamp behavior is preserved; the `scan_incomplete: bool`
companion field on IntegrityReport is the type-safe channel for
disambiguation; consumers requiring null-on-incomplete construct their
own representation from the bool + score pair. The clamp value `0.5`
remains intentionally overloaded; the `0.5`-or-null question stays
open as a future-design candidate. Future redesigns require the
parity-break ceremony per PARITY.md. Cross-reference: docs/score.md
§2.4 (Q4 closure note) + tests/contracts/test_scan_incomplete_clamp.py
(regression pin).

### Q5. The default pipeline silently lacks documented capabilities

Cross-modal correlation (subtitle/audio/metadata divergence) is listed as a supported mechanism but is opt-in and not wired into `ScanService().scan(path)` by default. The README and the report header now disclose this in v1.2; the question is whether default-off is the right policy long-term or whether v1.3 should make cross-modal default-on once the rule set stabilizes. Default-off preserves backward compatibility; default-on matches what the README's mechanism table implies.

**v1.7.0 closure-log data point #1 (Round 17, 2026-06-23):** Q5
disambiguated and substrate-actual policy documented in
`docs/cross_modal.md`. Bayyinah ships TWO correlation surfaces, not
one. Phase 12 `CorrelationEngine` (verse 2:282, two-witness) is
DEFAULT-ON: every `ScanService.scan()` invocation runs
`intra_file_correlate` and every `ScanService.scan_batch()` runs
`cross_file_correlate`. Phase 25+ `CrossModalCorrelationEngine`
(verse 2:164, stem-level) is OPT-IN: invoked explicitly via
`CrossModalCorrelationEngine().correlate(report)`. The v1.7.0
decision is to KEEP Phase 25+ opt-in pending three conditions:
(a) all five reserved future-work rule names ship detectors or close
explicitly; (b) a PARITY-break ceremony per `PARITY.md` is invoked
with calibration evidence on video/audio fixture corpus;
(c) `MIGRATION.md` documents downstream consumer impact. Verse 2:148
anchor: the scanner faces one default direction (Phase 12 default-on
cross-layer correlation); a second direction (Phase 25+ stem-level
correlation) is reserved opt-in. The v1.7.0 release pins this policy
via P1-P4 in `tests/contracts/test_cross_modal_policy.py` so a future
silent flip to default-on becomes a regression rather than a quiet
behavior change. Cross-reference: `docs/cross_modal.md` (canonical
policy) + `tests/contracts/test_cross_modal_policy.py` (regression
pin) + CHANGELOG [1.7.0].

### Q7. The demo counter is obfuscated, not anonymized

SHA-256 of IPv4 over a daily-rotating salt is brute-forceable by enumeration in seconds on commodity hardware once the salt is known. The README's claim that "cross-day correlation is impossible without the per-instance secret" is true only as long as the secret is never logged, leaked, or rotated in a way that retains the prior value. v1.2 corrects the language to "obfuscated, not anonymized." The structural fix is HyperLogLog or a Bloom filter -- counts without identifiers -- and is committed for v1.2. Q7 stays open until that lands.

### Q8. Test count is not test quality

1,782 tests is the published number. The taxonomy is fixture-pinning plus integration. Missing from the suite: mutation testing (do the tests fail when an analyzer is broken?), differential testing against `pdfid`, `oletools`, `yara`, `clamav` on a shared corpus, adversarial fuzzing of the `FileRouter` polyglot dispatch, property-based tests with Hypothesis on the score function (idempotence, monotonicity in finding severity). The two-witnesses principle the README invokes (Al-Baqarah 2:282) is currently witnessed only by the project's own fixtures. Q8 is which of these external witness layers gets prioritized for v1.3.

**v1.8.0 closure-log data point #1 (Round 18, 2026-06-23):** Q8
prioritization order documented in `docs/differential_testing.md` §3.
Priority 1 (pdfid) ships at v1.8.0 as
`tests/differential/test_pdfid_witness.py` wrapping Didier Stevens'
pdfid.py via the `DifferentialWitness` abstract base class declared
in `tests/differential/witness_contract.py`. The witness skips
cleanly with a documented install hint when pdfid is unavailable.
Priority 2 (oletools), Priority 3 (yara), Priority 4 (clamav)
remain queued per the prioritization rationale in
`docs/differential_testing.md` §3.2-§3.4 (threat-model overlap +
install-footprint cost). Property-based score-function tests ship
at v1.8.0 as `tests/contracts/test_score_properties.py` using
Hypothesis, pinning five score-function invariants per
`docs/differential_testing.md` §4: range, empty-list, idempotence,
monotonicity in finding count, saturation at zero, plus order
invariance. Mutation testing and FileRouter fuzzing remain
deferred. Verse 2:282 anchor: Bayyinah's existing fixture-pinning
tests witness Bayyinah's own behavior; the differential layer adds
the second witness the verse requires. Cross-reference:
`docs/differential_testing.md` (canonical architecture) +
`tests/differential/witness_contract.py` (DifferentialWitness ABC) +
`tests/differential/test_pdfid_witness.py` (Priority 1) +
`tests/contracts/test_score_properties.py` (Hypothesis pins) +
CHANGELOG [1.8.0].

### Q9. The cross-model audit shares failure modes

"Eight sessions, eight closing audits, zero open findings under the Munafiq Protocol cross-verification across three AI collaborators (Anthropic Claude, xAI Grok, Perplexity Computer)." Current LLMs share substantial failure modes (sycophancy, anchoring on prompt framing, agreement under social pressure). Three of them auditing the same artifact under the same framework reduces single-model variance but does not address shared bias. Q9 is whether the project should claim "audit-cleanness" at all in the absence of a human audit by someone paid to find holes, who does not accept the framework's premises.

### Q10. Strategic coupling of framework and engineering

The Quranic-principles section is load-bearing in the README. For Apache-2.0 OSS aiming at adoption in security teams, regulated industries, and academic citation, this couples adoption to acceptance of the framework. The engineering principles (deterministic byte-level checks, fail-closed defaults, additive-only invariants, fixture-pinned tests) stand without the framework -- the framework explains *why* these principles were chosen, not *whether* they hold. Q10 is whether a framework-free statement of the engineering principles should appear somewhere in `docs/`, alongside the framework-anchored README, for readers whose adoption is gated on it.

This is not a question about removing the framework. It is a question about whether the project's adoption ceiling is the framework's audience, and whether that is the intended ceiling.

**v1.9.0 closure-log data point #1 (Round 19, 2026-06-23):** Q10
closure target authored at `docs/principles.md` (expanded from the
v1.5.0 stub to full content per CODING_STRATEGY §6 v1.9.0). The
document states five engineering principles in framework-free
language: §1 Determinism, §2 Fail-closed defaults, §3 Additive-only
invariants, §4 Fixture-pinned tests, §5 Honest knowledge bounds.
Each principle is paired with its structural defense (the file or
test that enforces the principle) so a downstream consumer can
verify every claim mechanically against the source tree without
accepting any vocabulary outside standard software-engineering
terminology. The framework-anchored `README.md` remains the
canonical entry-point for readers who accept the framework basis;
`docs/principles.md` is the parallel entry-point for readers whose
adoption is gated on a framework-free statement. The Q10 thesis
verbatim per the document's own §6: "this document is consumable
without the framework." Verse 2:269 anchor: wisdom holds regardless
of frame; the engineering principles are wisdom statements verifiable
against the substrate. Cross-reference: `docs/principles.md`
(canonical Q10 closure document) + CHANGELOG [1.9.0].

### Q-PRO-3. Honest budget controller

The cost-class taxonomy at `domain/cost_classes.py` describes the
algorithmic shape of every mechanism with respect to one document
(class A structural address, class B indexed content walk, class C
cross-correlation, class D full re-parse). A budget-conscious caller
wants to set a ceiling on the cost class they will admit and know
honestly which mechanisms run and which are skipped. Q-PRO-3 is
whether a budget controller can be authored that reports honestly,
without redesigning the existing production / forensic scan modes or
silently skipping mechanisms.

**v1.6.0 closure-log data point #1 (Round 16, 2026-06-23):** Q-PRO-3
ships at v1.6.0 as a pure projection layer per `docs/budget.md`.
`application.budget_controller.plan_scan_budget(ceiling)` computes a
`BudgetPlan` partitioning `MECHANISM_REGISTRY` into `in_budget` and
`out_of_budget` against the ceiling, with `scan_incomplete_implied`
True whenever any mechanism is excluded. The honest accounting
property (Verse 2:188): a downstream caller that runs only the
in_budget subset MUST pass `scan_incomplete_implied` to
`apply_scan_incomplete_clamp` per `docs/score.md` §2.1, so the score
reflects truncation. The v1.6.0 release does NOT modify
`ScanService.scan()` signature; wiring the budget plan into the scan
call path is deferred to a later release with explicit parity-break
ceremony per `PARITY.md`. Cross-reference: `docs/budget.md` (canonical
contract) + `tests/contracts/test_budget_controller.py` (regression
pin) + CHANGELOG [1.6.0].

### Q-PRO-4. Supply-chain integrity is a different threat model

Supply-chain attacks compromise the pipeline by which a file or
binary came to exist (dependency substitution, build-system tampering,
provenance forgery, signing-key compromise). The ecosystem for that
threat model is mature: SPDX SBOM, CycloneDX SBOM, in-toto attestations,
Sigstore signing, SLSA framework levels. Q-PRO-4 is whether Bayyinah
should ingest these artifacts as primary witnesses, compose with them
at an operator workflow tier, or decline to address the supply-chain
question altogether.

**v1.6.0 closure-log data point #1 (Round 16, 2026-06-23):** Q-PRO-4
ships at v1.6.0 as a scope disposition per
`docs/supply_chain_disposition.md`. Supply-chain detection is OUT OF
SCOPE for v1.x and v2.x. The three-part rationale: (a) Bayyinah's
witnesses inspect file content; supply-chain witnesses inspect
provenance anchored outside the file. (b) The supply-chain ecosystem
is mature (ISO 5962:2021 SPDX, OWASP CycloneDX, CNCF in-toto, Linux
Foundation Sigstore, SLSA framework); the honest engineering decision
is composition not reimplementation. (c) The five immutable patent
surfaces describe content witnesses; extending them to provenance
witnesses would escalate to patent counsel before merge. v3.0+
enterprise tier per `ROADMAP_TO_V5.md` defines the composition
interface; that release would author its own disposition document
superseding this one. Cross-reference:
`docs/supply_chain_disposition.md` + CHANGELOG [1.6.0].

## Resolved

### Q6. The parser is the attack surface (Resolved in v1.2.1)

v1.2.1 wraps every scan in a subprocess with a 30-second wall-clock
timeout. Timed-out scans return ``scan_incomplete=True`` with verdict
``mughlaq``. Subprocess isolation means a pymupdf segfault no longer
crashes the API worker. The original v1.2 framing of Q6 (whether
v1.2's threat model is the right one and what isolation primitives
the v1.3 cloud deployment commits to) is preserved in the v1.2.1
CHANGELOG entry; v1.2.1 closure addresses the timeout and process-
isolation halves of that question. The deeper fix (seccomp-bpf,
dedicated scanning microservice, OS-level CPU rlimit per request)
remains on the v1.3 roadmap.
