# Cross-modal correlation policy (v1.7.0)

Canonical contract document for Bayyinah's two correlation surfaces.
Introduced at v1.7.0 (Round 17) per `CODING_STRATEGY_v1_2_4_to_v2_0.md`
§6 v1.7.0 Fatiha session.

Verse anchor: al-Baqarah 2:148 ("And for each is a direction toward
which it faces. So race to [all that is] good"). The architectural
reading: cross-modal correlation is a different "direction" the
scanner can face. The honest policy at v1.7.0 distinguishes the
direction the scanner currently faces from the direction reserved for
future stabilization, and documents why.

## §1 Two correlation surfaces

Bayyinah ships two distinct correlation engines at v1.7.0. Both are
public; their composition policies differ.

### §1.1 Phase 12 `CorrelationEngine` -- DEFAULT-ON

Located: `analyzers/correlation.py`
Verse anchor: al-Baqarah 2:282 (two-witness principle).

This engine is invoked automatically by `ScanService.scan()` on every
scan. After all analyzers complete their per-format walk, the engine
runs `intra_file_correlate` against the merged findings list and
emits `coordinated_concealment` findings when the same normalized
hidden-payload string appears in two or more findings with distinct
(mechanism, location) pairs.

`ScanService.scan_batch()` additionally invokes `cross_file_correlate`
after every per-file scan completes, emitting
`cross_format_payload_match` findings when the same payload appears
across distinct files.

The Phase 12 engine is the default cross-layer witness composer.
Callers do not need to opt in.

### §1.2 Phase 25+ `CrossModalCorrelationEngine` -- OPT-IN

Located: `analyzers/cross_modal_correlation.py`
Verse anchor: al-Baqarah 2:164 (reading the stems together).

This engine is a post-processor that consumes an already-scanned
`IntegrityReport` and emits additional findings against the
multi-stem containers that `VideoAnalyzer` and `AudioAnalyzer`
decomposed in earlier phases. Two active rules at v1.7.0:

- `cross_stem_inventory` -- always emitted; enumerates every stem the
  upstream analyzers extracted and notes the correlation rules
  applied.
- `cross_stem_undeclared_text` -- subtitle or lyric stem carries
  substantive text while the metadata stem is silent.

Five future-work rule names are reserved in `domain/config.py`
comments (`cross_stem_text_inconsistency`, `cross_stem_metadata_clash`,
`embedded_media_recursive_scan`, `cross_stem_coordinated_concealment`,
`cross_file_media_divergence`); detectors land in subsequent sessions
as the rule set stabilizes.

Opt-in invocation:

    from bayyinah import ScanService, CrossModalCorrelationEngine

    report = ScanService().scan(path)
    correlation_findings = CrossModalCorrelationEngine().correlate(report)
    report.findings.extend(correlation_findings)

## §2 Why Phase 25+ remains opt-in at v1.7.0

The Q5 question per `QUESTIONS.md` asks whether the cross-modal
default should remain off or flip to on. The v1.7.0 answer is "remain
opt-in" with three documented reasons:

### §2.1 Rule set calibration is not complete

The Phase 25+ docstring explicitly notes that the engine is "session
1" of a multi-session rule rollout. Two rules are active; five rule
names are reserved. Flipping the default to on before the reserved
rules ship would commit downstream consumers to an interface whose
finding shape is still moving.

### §2.2 PARITY discipline

Wiring the Phase 25+ engine into the default scan call path would
change the finding count on every multi-modal fixture in the test
suite (every video and audio fixture would gain at least one
`cross_stem_inventory` finding). That is a PARITY-affecting change
per `PARITY.md` and would require the five-step parity-break
ceremony. v1.7.0 ships at STANDARD audit-intensity per
`CODING_STRATEGY_v1_2_4_to_v2_0.md` §6 v1.7.0; PARITY-break ceremonies
require dedicated rounds with calibration evidence.

### §2.3 Phase 12 already provides default cross-layer correlation

The Phase 12 `CorrelationEngine` is default-on and provides the
two-witness correlation that the Q5 question's framing implied was
missing. The Phase 25+ engine is a different witness shape (stem-
level vs. payload-level); it is additive, not a replacement.

## §3 What the v1.7.0 closure does NOT do

The v1.7.0 release does NOT:

1. Modify `ScanService.scan()` or `ScanService.scan_batch()` to
   invoke `CrossModalCorrelationEngine`. Their behavior is unchanged.
2. Add new cross-modal mechanisms to `MECHANISM_REGISTRY`. The five
   existing entries (`audio_cross_stem_divergence`,
   `cross_format_payload_match`, `cross_stem_inventory`,
   `cross_stem_undeclared_text`, `video_cross_stem_divergence`)
   remain unchanged.
3. Remove the future-work rule name reservations in
   `domain/config.py`. Those names continue to mark the rule rollout
   path.
4. Add a `cross_modal: bool` parameter to `ScanService.scan()`. The
   opt-in surface is the `CrossModalCorrelationEngine().correlate()`
   call; no flag on the scanner.

## §4 Contract properties pinned at v1.7.0

Pinned by `tests/contracts/test_cross_modal_policy.py`. Modifications
that break any of these are regressions requiring the parity-break
ceremony per `PARITY.md`.

### §4.1 P1. Phase 12 default-on invariant

`ScanService` instantiated without an explicit `correlation_engine`
argument MUST have a `CorrelationEngine` instance attached to
`self.correlation_engine`. The Phase 12 engine remains in the
default scan call path at v1.7.0.

### §4.2 P2. Phase 25+ default-off invariant

The Phase 25+ `CrossModalCorrelationEngine` MUST NOT be invoked as a
side effect of `ScanService.scan()` or `ScanService.scan_batch()`.
Callers who want stem-level correlation invoke the engine explicitly.

### §4.3 P3. Public surface invariant

Both engines are exported by `analyzers.__init__`. The opt-in
invocation pattern documented in §1.2 must remain available to
downstream callers.

### §4.4 P4. Mechanism-registry stability

The five existing cross-modal mechanisms remain in
`MECHANISM_REGISTRY`. No additions or removals at v1.7.0.

## §5 Future-work conditions for default-on flip

A future release MAY wire `CrossModalCorrelationEngine` into the
default scan path. The conditions for that release:

1. All five reserved future-work rule names have shipping detectors,
   OR an explicit decision document closing the unused names.
2. A PARITY-break ceremony per `PARITY.md` is invoked with calibration
   evidence on a video and audio fixture corpus.
3. The migration note in `MIGRATION.md` documents downstream
   consumer impact (every multi-modal scan gains at least one
   `cross_stem_inventory` finding).
4. A bumped minor version reflects the surface change.

Until those conditions are met, Phase 25+ remains opt-in.

## §6 Cross-references

- `analyzers/correlation.py` -- Phase 12 default-on engine.
- `analyzers/cross_modal_correlation.py` -- Phase 25+ opt-in engine.
- `application/scan_service.py` -- default invocation site for Phase
  12 engine (lines 674-683 `intra_file_correlate`, line 817+
  `cross_file_correlate`).
- `domain/config.py` -- `MECHANISM_REGISTRY` cross-modal entries +
  future-work reserved names.
- `tests/contracts/test_cross_modal_policy.py` -- contract pin tests
  for P1-P4.
- `QUESTIONS.md` Q5 -- closure log entry citing this document.
- `PARITY.md` -- parity-break ceremony required for default-on flip.
- `CODING_STRATEGY_v1_2_4_to_v2_0.md` §6 v1.7.0 -- release plan.
- `docs/budget.md` -- Q-PRO-3 closure (companion document, v1.6.0).
