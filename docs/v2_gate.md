# Bayyinah v2.0.0 Gate Criteria

**Version:** v2.0.0 (Round 20 commercialization gate).
**Authority:** QUESTIONS.md Q9 closure + CODING_STRATEGY §6 v2.0.0 +
ROADMAP_TO_V5.md v2.0 commercialization gate.
**Status:** AUTHORED.

This document is the v2.0.0 commercialization gate. It declares
three categories of commitments: (a) what is true at v2.0.0 as
shipped, (b) what must be true after an external human audit
before the project marks itself as commercialization-ready and
opens commercial dispatch, (c) what counts as a commercialization-
ready signal so the boundary between research-preview and
commercial offering is not silently crossed.

Verse anchor: al-Baqarah 2:281 ("And fear a Day when you will be
returned to Allah. Then every soul will be compensated for what
it earned, and they will not be treated unjustly"). The
architectural reading: accountability has a settlement event;
v2.0.0 is the settlement event in the project's major-version arc.
The terms below are the settlement criteria.

## §1 What is true at v2.0.0 as shipped

The v2.0.0 release closes the v1.x interpretive question arc with
documented closures filed in `QUESTIONS.md`:

| Question | Closure location |
|---|---|
| Q1 score-function blind spot | `KNOWN_LIMITS.md` (v1.5.0) |
| Q2 PARITY contract calibration | `PARITY.md` ledger (v1.3.0 data point) |
| Q3 score-function shape pin | `docs/score.md` (v1.4.0) |
| Q4 SCAN_INCOMPLETE_CLAMP semantics | `docs/score.md` §2 (v1.4.0) |
| Q5 cross-modal correlation policy | `docs/cross_modal.md` (v1.7.0) |
| Q6 parser attack surface | v1.2.1 subprocess timeout closure |
| Q7 demo telemetry obfuscation | `KNOWN_LIMITS.md` §3 carry-forward |
| Q8 differential testing matrix | `docs/differential_testing.md` (v1.8.0) |
| Q9 external human audit | this document (v2.0.0) |
| Q10 framework-free principles | `docs/principles.md` (v1.9.0) |
| Q-PRO-3 honest budget controller | `docs/budget.md` (v1.6.0) |
| Q-PRO-4 supply-chain disposition | `docs/supply_chain_disposition.md` (v1.6.0) |

The substrate is at v2.0.0 with `MECHANISM_REGISTRY` containing
159 entries, the five-verdict mechanic intact
(sahih/mushtabih/mukhfi/munafiq/mughlaq), PARITY contract
byte-identical against `bayyinah_v0` / `bayyinah_v0_1` on every
Phase 0 fixture, and the contract pin tests in `tests/contracts/`
passing across the v1.4.0-v1.9.0 documented surfaces.

The five engineering principles in `docs/principles.md` are paired
with structural defenses that run in the CI suite. The five
immutable patent surfaces (analyzer registry 130, layer-
classification 132/136, producer-signature calibration 134,
verdict aggregator 150, witness emitter 160) are intact;
modifications escalate to counsel per the patent invariant clause.

## §2 What must be true before commercial dispatch

The v2.0.0 version bump in `pyproject.toml` is necessary but not
sufficient for commercial dispatch. The following commitments must
land before the project markets itself as commercialization-ready:

### §2.1 External human audit (Q9 closure)

Q9 in `QUESTIONS.md` asks whether the project should claim "audit-
cleanness" in the absence of a human audit by someone paid to find
holes who does not accept the framework's premises. The v2.0.0
gate answer: NO. The cross-model AI audit chain through Round 19
is the project's internal audit-of-self; it does not substitute
for the external human audit Q9 requires.

The external human audit must satisfy four criteria:

1. **Auditor independence**: the auditor is paid through a
   commercial contract, has no equity in the project, and has no
   prior contribution to the framework or to Bayyinah code.
2. **Framework-free engagement**: the auditor is engaged against
   `docs/principles.md` (Q10 closure) rather than the framework-
   anchored README. The auditor verifies the engineering claims
   without being asked to accept the framework's vocabulary or
   epistemology.
3. **Hostile mandate**: the auditor's contract reward structure
   pays for findings, not for sign-off. An audit that returns
   zero findings is the failure mode (it suggests the auditor
   did not look hard enough), not the success mode.
4. **Findings disposition**: the auditor's findings are absorbed
   into the codebase via the same parity-break ceremony documented
   in `PARITY.md`. Findings the project disputes get a public
   dispute response in the same release that absorbs the
   non-disputed findings.

Until these four criteria are satisfied, the project's published
claim shape is "audit-of-self complete through Round 19 across
four AI vendors (Anthropic, OpenAI, Google, Perplexity); external
human audit pending Q9 closure." This is the v2.0.0 honest
claim; "audit-clean" is not.

### §2.2 Recursive self-verification

Bayyinah's thesis is that a scanner detects performed alignment by
comparing what a file displays against what it contains. v2.0.0
applies the thesis to Bayyinah itself: the release artifacts
(`README.md`, `CHANGELOG.md`, `KNOWN_LIMITS.md`, `QUESTIONS.md`,
`RETIREMENT_LEDGER.md`, `MIGRATION.md`, the `docs/` files, the
top-level `*.md` strategy documents) are scanned by Bayyinah on
every CI run. A finding fired by Bayyinah's own analyzers on its
own release documents is a structural failure: either the analyzer
has a false-positive that needs calibration, or the release
documents carry concealment shapes that need correction.

The structural defense is `tests/recursive_self_verification/test_self_scan.py`.
The test enumerates the release-document corpus and asserts that
every document scans clean (no findings) with `scan_incomplete=False`
and verdict `sahih` or `mushtabih` at most.

A false-positive flagged by the recursive self-verification test
goes through the same Round 12 calibration-corrective discipline
that closed the openaction destination-vs-action filter and the
tounicode_anomaly producer suppression. A genuine concealment
shape detected in a release document is a Tier 1 release blocker
absorbed before push.

### §2.3 Commercialization-ready signal

The project crosses from research-preview to commercial offering
only when all three signals are present:

1. **External human audit complete**: §2.1 criteria satisfied, the
   auditor's findings absorbed, the auditor's commission paid in
   full.
2. **Recursive self-verification CI green**: every release
   document scans clean on the CI run that cuts the
   commercialization-ready tag.
3. **`ROADMAP_TO_V5.md` v2.0 gate row marked CLOSED**: the
   companion strategy document tracking the v2.0 → v3.0 enterprise
   tier arc records the gate-close event with the same SHA as the
   release tag.

Until all three signals are present, the project's marketing
language is "research preview at v2.0.0 with external audit
pending" rather than "commercially-ready scanner."

## §3 What this gate does NOT do

The v2.0.0 gate does NOT:

1. Schedule the external audit. The audit happens through Bilal's
   commercial coordination with an external security firm or
   independent auditor. The patch documents the criteria; the
   audit itself is out of band.
2. Pre-commit to absorbing findings the project disputes. §2.1
   criterion 4 reserves the right to dispute publicly; the
   disposition is per-finding, not blanket.
3. Pin the audit cost or timeline. Those depend on the auditor's
   commercial terms and are not appropriate for a public gate
   document.
4. Replace the framework. The framework-anchored README remains
   the canonical project entry-point per the v1.9.0 Q10 closure;
   the framework-free `docs/principles.md` remains the parallel
   entry-point. The external audit engages against the framework-
   free statement per §2.1 criterion 2.
5. Remove anything from the codebase. v2.0.0 is additive per the
   `docs/principles.md` §3 additive-only invariants; the major-
   version bump is the gate marker, not a license for silent
   removal. Any removal at v2.0.0 or later goes through the
   PARITY.md ceremony and the MIGRATION.md downstream-consumer
   note.

## §4 PARITY contract

PARITY is unaffected by v2.0.0. No analyzer is added or modified;
no mechanism enters or leaves `MECHANISM_REGISTRY`; no score-
function behavior changes. `bayyinah.scan_pdf(path).to_dict() ==
bayyinah_v0.scan_pdf(path).to_dict()` continues to hold byte-
identically on every Phase 0 fixture.

The PARITY-break ceremony per `PARITY.md` continues to apply to
any future modification at v2.x and beyond. The major-version
bump does not waive the ceremony.

## §5 Cross-references

- `docs/principles.md` -- framework-free engineering principles
  the external auditor engages against.
- `tests/recursive_self_verification/test_self_scan.py` -- the
  CI-enforced recursive self-verification per §2.2.
- `QUESTIONS.md` Q9 -- closure-log entry citing this document.
- `KNOWN_LIMITS.md` -- the blind-spot publication carried into
  v2.0.0.
- `ROADMAP_TO_V5.md` -- the v2.0 → v3.0 enterprise tier arc.
- `STRATEGY_TO_V2.md` -- the strategic plan whose v2.0.0 gate
  this document closes.
- `PARITY.md` -- the ceremony that applies to any post-v2.0.0
  modification.
- `MIGRATION.md` -- the downstream-consumer note for any
  post-v2.0.0 removal.
- `CODING_STRATEGY_v1_2_4_to_v2_0.md` §6 v2.0.0 -- release plan
  (HEAVY audit-intensity).
- The patent invariant clause -- the five immutable surfaces
  that remain intact across the v2.0.0 boundary.
