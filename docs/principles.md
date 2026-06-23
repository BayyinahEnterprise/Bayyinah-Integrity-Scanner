# Bayyinah Engineering Principles (Framework-Free Statement)

**Version:** v1.9.0 (Q10 closure target authored).
**Authority:** QUESTIONS.md Q10 closure + CODING_STRATEGY §6 v1.9.0.
**Status:** AUTHORED.

This document is the framework-free engineering principles statement
for the Bayyinah Integrity Scanner. It states the engineering claims
that the project commits to, in language that holds without requiring
PMD vocabulary, the Bayyinah Audit Framework vocabulary, the Munafiq
Protocol vocabulary, or Quranic vocabulary to consume. The framework-
anchored `README.md` remains the canonical project entry-point for
readers who accept the framework basis; this file is the parallel
entry-point for readers whose adoption is gated on a framework-free
statement.

The Q10 thesis: the engineering principles below stand without the
framework. The framework explains why these principles were chosen;
the principles themselves are verifiable against the source tree
without reference to that explanation. Readers who reach this
document via security-team review, regulated-industry compliance
review, or academic citation can verify every claim mechanically
against the live repo.

The principles are stated as commitments, with the structural
defense (the file or test that enforces the principle) cited
inline. A modification to the codebase that breaks a structural
defense is a regression and must go through the parity-break
ceremony documented in `PARITY.md`.

## §1 Determinism

### §1.1 The commitment

For any input file F, repeated invocations of `bayyinah.scan_pdf(F)`
on the same machine, in the same environment, with the same code
revision, produce byte-identical `IntegrityReport.to_dict()` output.
Repeated invocations across machines and operating systems produce
byte-identical output when the runtime versions match.

### §1.2 The structural defense

The PARITY contract documented in `PARITY.md` asserts:

    bayyinah.scan_pdf(path).to_dict()
        == bayyinah_v0.scan_pdf(path).to_dict()
        == bayyinah_v0_1.scan_pdf(path).to_dict()

for every fixture in the Phase 0 fixture corpus. The reference
scanners `bayyinah_v0` and `bayyinah_v0_1` are preserved verbatim
in the source tree and never modified. The contemporary scanner
`bayyinah` evolves; the parity test asserts that evolution does
not silently change observable output. When a v0 finding, score,
error message, or output shape is demonstrated to be incorrect,
the parity baseline updates via the five-step parity-break
procedure in `PARITY.md`: open a tracking issue, cross-reference
from `CHANGELOG.md`, update affected Phase 0 fixtures, update
`tests/test_fixtures.py::test_v0_v01_parity`, bump the minor
version.

### §1.3 Why determinism matters

Downstream consumers integrate Bayyinah into security pipelines
and compliance workflows where the same input must always produce
the same audit signal. A scanner that returns different findings
on re-run cannot be trusted as a gate. Determinism is the
precondition for every other property the scanner claims.

### §1.4 Cross-references

`PARITY.md`, `tests/test_fixtures.py::test_v0_v01_parity`,
`CHANGELOG.md` parity-break ledger entries (v1.3.0
tounicode_anomaly tier reclassification is the most recent data
point).

## §2 Fail-closed defaults

### §2.1 The commitment

When the scanner cannot complete a layer of analysis, it reports
the incompleteness rather than returning a clean output. The
scan-incomplete signal is a first-class field on `IntegrityReport`.
The integrity score clamps to a documented value
(`SCAN_INCOMPLETE_CLAMP = 0.5`) whenever any analyzer reports
incomplete coverage, so a downstream consumer reading only the
score cannot mistake an incomplete scan for a clean one.

### §2.2 The structural defense

The clamp truth table is pinned by
`tests/contracts/test_scan_incomplete_clamp.py`. The clamp constant
is exported from `domain.config` and verified at module load.
Scan errors surface as `scan_error` findings with documented tier
and confidence rather than as silent passes.

`docs/score.md` documents the score-function contract that
fail-closed defaults rely on:

- `compute_muwazana_score([])` returns 1.0 (perfect score for an
  empty finding list).
- `apply_scan_incomplete_clamp(score, scan_incomplete=True)`
  returns 0.5 for any input score above 0.5.
- The `scan_incomplete: bool` companion field on `IntegrityReport`
  is the type-safe disambiguation channel for downstream consumers
  who want to distinguish "half-dirty file" from "unscanned half."

### §2.3 Why fail-closed matters

A scanner that silently passes on errors is worse than no scanner:
it gives the consumer false confidence. Fail-closed defaults make
the limitations of every scan visible to the consumer, so the
consumer can decide whether the partial information is sufficient
for their use case.

### §2.4 Cross-references

`domain/config.py` `SCAN_INCOMPLETE_CLAMP`,
`domain/value_objects.py` `apply_scan_incomplete_clamp`,
`tests/contracts/test_scan_incomplete_clamp.py`,
`docs/score.md` §2.

## §3 Additive-only invariants

### §3.1 The commitment

The public Python surface (`bayyinah.__all__`, the analyzer registry,
the mechanism registry, the verdict aggregator, the report schema)
grows monotonically across releases at the patch and minor level.
Removals require a major version bump. Tier reclassifications,
mechanism removals, and finding-shape changes are parity-break
events requiring the ceremony documented in `PARITY.md`.

The `MECHANISM_REGISTRY` is a frozenset of mechanism names; every
mechanism that has ever shipped remains in the registry unless
formally retired via a documented procedure. At v1.9.0 the
registry has 159 entries.

### §3.2 The structural defense

`tests/test_public_surface.py` (and related per-version surface
pins) assert that the documented public surface frozenset is
exactly the names exported by each module. A name added without
updating the surface pin breaks the test. A name removed without
the parity-break ceremony breaks the test.

The mechanism registry coherence test asserts that:

- Every entry in `MECHANISM_REGISTRY` has an entry in
  `MECHANISM_COST_CLASS` (the cost-class taxonomy).
- Every entry in `MECHANISM_COST_CLASS` is a registered mechanism.

This bidirectional coherence runs at module import; the scanner
fails to start if the taxonomy and registry have drifted.

The release-readiness test
`tests/test_release_readiness.py::test_pyproject_version_matches_package_version`
asserts that `pyproject.toml` and `bayyinah/__init__.py` `__version__`
are coherent at every release, so the additive-only contract is
anchored to a single version number. The
`tests/test_requirements_dev_sync.py` test asserts that
`requirements-dev.txt` and `pyproject.toml` `[project.optional-dependencies]
dev` carry identical entries, so the dependency-manifest surface is
itself additive-only across releases.

### §3.3 Why additive-only matters

Downstream consumers pin to specific mechanism names, finding
shapes, and public-API symbols. A scanner that silently removes or
renames a mechanism breaks every consumer that integrated against
it. The additive-only invariant guarantees that consumers can
upgrade across patch and minor versions without rewriting their
integration. Breaking changes require a major version bump and
explicit migration documentation in `MIGRATION.md`.

### §3.4 Cross-references

`domain/config.py` `MECHANISM_REGISTRY`,
`domain/cost_classes.py` `MECHANISM_COST_CLASS`,
`tests/test_public_surface.py`,
`tests/test_release_readiness.py`,
`tests/test_requirements_dev_sync.py`,
`PARITY.md` parity-break procedure,
`MIGRATION.md`,
`docs/score.md` and `docs/budget.md` and `docs/cross_modal.md`
for the contract pins that hold across additive-only growth.

## §4 Fixture-pinned tests

### §4.1 The commitment

Every detection mechanism in `MECHANISM_REGISTRY` has at least one
fixture in `tests/fixtures/` that, when scanned, produces the
mechanism's finding. The fixture is checked into the source tree.
A regression that causes the mechanism to stop firing on its
fixture breaks the test.

The five-place documentation pattern, introduced at the v1.2.4
release-discipline cycle, asserts that every documented mechanism
has parallel entries in five locations: `CHANGELOG.md`,
`README.md` (or the relevant document table), the fixture file,
the pinning test, and the `MECHANISM_REGISTRY` entry. Drift
between these places is the structural drift the test discipline
catches.

### §4.2 The structural defense

`tests/test_fixtures.py` and the per-format test modules under
`tests/analyzers/` enumerate the fixture corpus and assert that
each fixture produces the expected finding set. New mechanisms
ship with their fixtures or do not ship.

At v1.8.0 the fixture-pinning layer was extended with a
differential testing matrix per `docs/differential_testing.md`:
external tools (priority 1 pdfid; priorities 2-4 queued) act as
independent witnesses to the same fixture corpus, surfacing
divergence between Bayyinah and the external tool. Divergence is
informational, not assertional; the two-witnesses logic gives the
consumer additional confidence in findings both witnesses agree
on.

Hypothesis-based property tests at v1.8.0 pin five score-function
invariants over the strategy space rather than at finite fixture
points: range, empty-list, idempotence, monotonicity in finding
count, saturation at zero (see `docs/differential_testing.md` §4
and `tests/contracts/test_score_properties.py`).

### §4.3 Why fixture-pinned tests matter

Test count is not test quality. A suite of 1,900 tests that all
exercise the same code path proves less than a suite of 100 tests
that each pin a distinct claim. Fixture-pinned tests force each
detection mechanism to declare its observable evidence in a file
that the test suite re-reads on every run. The external-witness
extension at v1.8.0 adds independent observers to that evidence
set, so the suite is not solely witnessing its own behavior.

### §4.4 Cross-references

`tests/test_fixtures.py`,
`tests/analyzers/`,
`docs/differential_testing.md`,
`tests/contracts/test_score_properties.py`,
`tests/differential/witness_contract.py`,
`tests/differential/test_pdfid_witness.py`.

## §5 Honest knowledge bounds

### §5.1 The commitment

The scanner publishes the shape of the input it cannot detect. The
canonical document is `KNOWN_LIMITS.md` at the repo root, which
enumerates nine limitation classes (score-function blind spot,
default-pipeline capability disclosure, demo telemetry obfuscation
boundary, test-count versus test-quality gap, cross-model audit
shared failure modes, framework-engineering coupling, format-
coverage holes, deferred mechanism work, parity-break ledger
caveats). The list is empirically grounded against the
`CHANGELOG.md`, `QUESTIONS.md`, and `RETIREMENT_LEDGER.md` history;
no hypothetical limitations padded for narrative balance.

### §5.2 The structural defense

`KNOWN_LIMITS.md` is committed to the source tree at the repo root
where every project visitor sees it. The file is referenced from
`CHANGELOG.md` v1.5.0 release notes and from `QUESTIONS.md` Q1
closure-log. A modification to detection behavior that closes one
of the limitations is documented as a closure in both files; a
modification that opens a new limitation class is added to
`KNOWN_LIMITS.md` as part of the same release.

The Q-PRO-4 scope disposition in `docs/supply_chain_disposition.md`
applies the same publication discipline to scope decisions:
supply-chain detection (SBOM, in-toto, Sigstore, SLSA) is OUT OF
SCOPE for v1.x and v2.x, declared explicitly rather than left
ambiguous. The Q5 cross-modal correlation policy in
`docs/cross_modal.md` declares the substrate-actual default policy
(Phase 12 default-on, Phase 25+ opt-in) and the future-flip
conditions, so a downstream consumer can plan migrations against
a documented surface.

### §5.3 Why honest knowledge bounds matter

A scanner that claims complete coverage of its threat model is
harder to attack than one that does not; a scanner that publishes
the shape of inputs it cannot detect is harder to attack than one
that claims complete coverage. The honest publication of blind
spots invites the security community to bring those inputs into
the test corpus, where they get fixtures, mechanisms, and
documentation; the dishonest claim of complete coverage hides the
attack surface from the people best positioned to close it.

### §5.4 Cross-references

`KNOWN_LIMITS.md`,
`QUESTIONS.md` (live list of open interpretive questions),
`docs/supply_chain_disposition.md`,
`docs/cross_modal.md` §5 (future-flip conditions),
`docs/budget.md` §3 (v1.6.0 scope boundary).

## §6 Closure cadence

The principles above hold at v1.9.0 (this document's authoring
release). Subsequent release notes that touch any of the five
principles MUST cross-reference this document and the relevant
structural defense. A principle that ceases to hold is removed
from this document as part of the release that removes it; a
principle that gains a stronger structural defense (a new test,
a new contract pin, a new external witness) is updated in this
document as part of the release that adds the defense.

The Q10 thesis: this document is consumable without the framework.
Readers who reach Bayyinah via security review, compliance review,
or academic citation can verify every claim in this document
against the source tree without accepting any vocabulary outside
standard software-engineering terminology.

The framework-anchored `README.md` remains the canonical entry-
point for readers who accept the framework basis. This document
is the parallel entry-point. The two coexist; neither replaces
the other.

## §7 Cross-references summary

| Principle | Structural defense |
|---|---|
| §1 Determinism | `PARITY.md`, `tests/test_fixtures.py::test_v0_v01_parity` |
| §2 Fail-closed defaults | `tests/contracts/test_scan_incomplete_clamp.py`, `docs/score.md` |
| §3 Additive-only invariants | `tests/test_public_surface.py`, `tests/test_release_readiness.py`, `tests/test_requirements_dev_sync.py` |
| §4 Fixture-pinned tests | `tests/test_fixtures.py`, `tests/differential/`, `tests/contracts/test_score_properties.py`, `docs/differential_testing.md` |
| §5 Honest knowledge bounds | `KNOWN_LIMITS.md`, `QUESTIONS.md`, `docs/supply_chain_disposition.md`, `docs/cross_modal.md`, `docs/budget.md` |
