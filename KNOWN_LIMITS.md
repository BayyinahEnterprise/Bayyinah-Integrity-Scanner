# Bayyinah Known Limitations

**Version:** v1.5.0 inaugural (Round 15 audit-of-self, Q1 closure).
**Verse anchor:** al-Baqarah 2:32 -- "we have no knowledge except what You have taught us."
**Authority:** QUESTIONS.md Q1 closure-log discipline + CODING_STRATEGY §6 v1.5.0 Cow Episode anchor.

This document enumerates KNOWN LIMITATIONS of the Bayyinah Integrity Scanner. Per Cow Episode anchor, every entry below is empirically grounded -- backed by a CHANGELOG entry, RETIREMENT_LEDGER deferral, or QUESTIONS.md open-question reference. No hypothetical limitations. No padding.

A scanner that publishes the shape of the input it cannot see is harder to attack than one that claims completeness. The Q1 thesis (per QUESTIONS.md): a scanner that publishes its blind spots is more honest than one that does not.

## §1 Score-function blind spot (Q1 closure)

**Limitation:** the default pipeline can produce `score == 1.0` on a document carrying concealed payload IF every concealment mechanism in the document is outside the v1.2.4 + v1.3.0 + v1.4.0 detector inventory.

**Construction method (general form; no public fixture published at v1.5.0):**

The score function is `clamp(1.0 - sum(severity * confidence for f in findings), 0, 1)` (see `docs/score.md` §1). If the `findings` list is empty, the score is `1.0`. The function is monotonic in findings and severity but does NOT encode coverage. An adversarial document constructed entirely from concealment mechanisms NOT in the current MECHANISM_REGISTRY (159 mechanisms at v1.4.0) emits an empty findings list and scores `1.0`. The known classes of mechanism NOT yet in the registry include:

- multi-layer integrity traps surfaced by the 2026-05-04 red-team probe (4 CRITICAL silent-pass + 5 HIGH partial-catches; deferred to v1.2.6 bridge-tag per RETIREMENT_LEDGER Round 11 in-progress entry pending project-lead provision of the red-team probe document)
- ML model substrate concealment (ONNX/TensorFlow/PyTorch deferred to v3.0+ per ROADMAP_TO_V5 §3 + provisional patent Claim 5)
- audio/video signal-level concealment (FileKind enum entries 14-19 routed but not signal-level-decomposed; deferred to v3.0+ per CODING_STRATEGY §8 stem extraction principle calibration constraint)
- source-code substrate concealment (furqan-lint companion provisional; deferred to v4.0 per ROADMAP_TO_V5 §5)
- novel concealment mechanisms not surfaced in any audit round to date

**Closure scope:** Q1 closure at v1.5.0 declares the BLIND SPOT GENERAL FORM publicly. Construction of a specific adversarial fixture demonstrating `score == 1.0` on a concealed-payload document is the next-phase v1.6.0 / v1.7.0 / v1.8.0 work as the substrate matures. The honest publication of the blind spot at this version IS the v1.5.0 Q1 closure; the empirical adversarial fixture follows.

**Cross-reference:** QUESTIONS.md Q1 + docs/score.md §1 + CODING_STRATEGY §6 v1.5.0.

## §2 Default-pipeline capability disclosure (Q5 carry-forward)

**Limitation:** `ScanService().scan(path)` does NOT enable cross-modal correlation by default at v1.4.0; it is opt-in. The README and report header disclose this in v1.2.x onward.

**Empirical evidence:** README.md cross-modal correlation section (per v1.2 disclosure update); `analyzers/cross_modal_correlation.py` exists in the registry but is opt-in per the scan service contract.

**Closure scope:** Q5 disposition (whether default-off remains long-term or whether v1.7.0 makes cross-modal default-on once the rule set stabilizes) is open per QUESTIONS.md Q5. Default-off preserves backward compatibility; default-on matches the README's mechanism table implication.

**Cross-reference:** QUESTIONS.md Q5 + analyzers/cross_modal_correlation.py + CODING_STRATEGY §6 v1.7.0 (cross-modal correlation default disposition).

## §3 Demo telemetry obfuscation (Q7 carry-forward)

**Limitation:** the demo bayyinah.dev visitor counter uses SHA-256 of IPv4 over a daily-rotating salt. This is obfuscation, not anonymization. The hash is brute-forceable by IPv4-space enumeration on commodity hardware within seconds once the salt is known.

**Empirical evidence:** QUESTIONS.md Q7 + v1.2 README language correction ("obfuscated, not anonymized").

**Closure scope:** the structural fix is HyperLogLog or a Bloom filter (counts without identifiers). Committed for a future v1.2.x patch per Q7. Q7 stays open until the structural fix lands.

**Cross-reference:** QUESTIONS.md Q7.

## §4 Test count is not test quality (Q8 carry-forward)

**Limitation:** the test suite (1,837+ pytest tests per FRAMEWORK.md §3) is fixture-pinning plus integration. It does NOT include:

- mutation testing (do tests fail when an analyzer is broken?)
- differential testing against pdfid / oletools / yara / clamav on a shared corpus
- adversarial fuzzing of the FileRouter polyglot dispatch
- property-based tests with Hypothesis on the score function (idempotence pinned at v1.4.0 contract; broader properties not exercised)

**Empirical evidence:** QUESTIONS.md Q8 + tests/ directory contents at v1.4.0.

**Closure scope:** the differential testing matrix vs pdfid + oletools + yara + clamav is the v1.8.0 release deliverable per CODING_STRATEGY §6 v1.8.0. The other Q8 categories (mutation, fuzzing, property-based) remain open and queued.

**Cross-reference:** QUESTIONS.md Q8 + CODING_STRATEGY §6 v1.8.0.

## §5 Cross-model audit shared failure modes (Q9 carry-forward)

**Limitation:** the four-vendor cross-rotation pool (Anthropic Claude + OpenAI ChatGPT + Google Gemini + Perplexity per PMD v1.8 §3B.3) provides architectural diversity but does NOT guarantee independence of failure modes. All four vendors share certain training-data biases. A verification architecture including models trained on substantially different data distributions would provide stronger evidence of methodology-independent validity.

**Empirical evidence:** QUESTIONS.md Q9 + cycle-1+P + cycle-1+P+P empirical observations (Gemini WL24 substrate-misread instances; ChatGPT consistent classification; Perplexity consistent classification; Claude producer-discount per PMD §3A.12.4).

**Closure scope:** the v2.0.0 external human audit (Round 20 per CODING_STRATEGY §6 v2.0.0) is the architectural answer to Q9 -- a human auditor provides the independence of failure modes that cross-vendor LLM rotation cannot. The external audit ships at v2.0.0 per the commercialization gate.

**Cross-reference:** QUESTIONS.md Q9 + PMD v1.8 §3B.3 + CODING_STRATEGY §6 v2.0.0.

## §6 Strategic coupling of framework and engineering (Q10 carry-forward)

**Limitation:** README.md's load-bearing Quranic-principles section couples adoption to acceptance of the framework. For Apache-2.0 OSS aiming at adoption in security teams, regulated industries, and academic citation, this is a barrier for readers whose adoption is gated on it.

**Empirical evidence:** QUESTIONS.md Q10 + README.md structure at v1.4.0.

**Closure scope:** docs/principles.md (framework-free engineering principles statement) is the v1.9.0 deliverable per CODING_STRATEGY §6 v1.9.0. Stub authored at v1.5.0; full content at v1.9.0.

**Cross-reference:** QUESTIONS.md Q10 + CODING_STRATEGY §6 v1.9.0 + docs/principles.md (stub).

## §7 Format-coverage holes (per FileKind enum)

**Limitation:** the FileKind enum at v1.4.0 declares 20 entries (per REPO_SUBSTRATE_PINNED §2 + CODING_STRATEGY §M+1.2). The 13 active document-format kinds are in scope. The remaining 6 substantive kinds (3 video + 3 audio formats: VIDEO_MOV, VIDEO_WEBM, VIDEO_MKV, AUDIO_WAV, AUDIO_FLAC, AUDIO_OGG) are routed by `infrastructure/file_router.py` but signal-level decomposition is deferred to v3.0+.

**Empirical evidence:** infrastructure/file_router.py FileKind enum + CODING_STRATEGY §8 stem extraction principle ("Container-level extraction by default. Signal-level extraction is registered as future work with explicit dependency gates").

**Closure scope:** signal-level audio/video analyzers require ML models (audio stem separation, video object detection, OCR for raster-embedded text) -- explicitly deferred to v3.0+ per CODING_STRATEGY §8 calibration constraint. Container-level metadata for these formats is already supported at v1.4.0.

**Cross-reference:** infrastructure/file_router.py + CODING_STRATEGY §8 + ROADMAP_TO_V5 §3.

## §8 Round 11 detector-gap carry-forward (multi-layer integrity traps)

**Limitation:** the 2026-05-04 red-team probe of bayyinah.dev v1.2.3 surfaced 4 CRITICAL silent-pass + 5 HIGH partial-catch findings against multi-layer integrity traps. v1.2.5 scaffolded the corpus structure (tests/fixtures/round11/README.md); the closure mechanisms are DEFERRED to v1.2.6 bridge-tag work pending project-lead provision of the red-team probe document.

**Empirical evidence:** RETIREMENT_LEDGER.md Round 11 in-progress entry + tests/fixtures/round11/README.md + CHANGELOG.md [1.2.5] section.

**Closure scope:** v1.2.6 bridge-tag work pending the red-team probe document. Best-judgement trap-class hypotheses are recorded in tests/fixtures/round11/README.md and RETIREMENT_LEDGER Round 11 entry. Not canonical; project-lead disposition refines against the actual probe substrate.

**Cross-reference:** RETIREMENT_LEDGER Round 11 + CHANGELOG [1.2.5] + tests/fixtures/round11/README.md.

## §9 PARITY-break ledger gaps

**Limitation:** the v0 + v0_1 reference scanners are FROZEN historical anchors. They continue emitting the pre-Round-13 behavior for tounicode_anomaly (tier=1). The modular bayyinah.scan_pdf emits the Round 13 corrected behavior (tier=2). The asymmetric parity is admitted via the documented `_v1_3_0_tounicode_tier_remap` in tests/test_integration.py per PARITY.md "Parity-break ledger" v1.3.0 entry. Consumers reading v0 or v0_1 output directly (rather than the modular API) will receive the pre-Round-13 tier.

**Empirical evidence:** PARITY.md "Parity-break ledger" v1.3.0 entry + tests/test_integration.py `_v1_3_0_tounicode_tier_remap` + bayyinah_v0.py + bayyinah_v0_1.py (frozen).

**Closure scope:** the v0 + v0_1 reference scanners are intentionally frozen. Consumers needing the v1.3.0+ behavior use the modular `bayyinah.scan_pdf` public API. Migration is documented in MIGRATION.md v1.2.x -> v1.3.0 section.

**Cross-reference:** PARITY.md + tests/test_integration.py + MIGRATION.md.

## §10 What this document is NOT

- A complete enumeration of all possible adversarial inputs (no such enumeration exists).
- A statement of guarantees about what Bayyinah catches (the Q1 thesis is precisely that no such guarantees exist).
- A scope-creep vehicle for v1.5.0 (per CODING_STRATEGY §6 v1.5.0 Cow Episode: empirical limitations only; no hypothetical limitations; if no CHANGELOG or QUESTIONS.md reference, the limitation is not in scope).

## §11 Closure cadence

Per CODING_STRATEGY §10 successor work + ROADMAP_TO_V5 arcs:

- v1.5.0: this document authored; Q1 closure data point #1 filed.
- v1.6.0: §1 score-function blind-spot construction method may be sharpened by Q-PRO-3 honest budget controller work.
- v1.7.0: §2 default-pipeline capability disclosure (Q5) is disposed per cross-modal default analysis.
- v1.8.0: §4 test-count-vs-test-quality (Q8 partial) is closed by the differential testing matrix.
- v1.9.0: §6 strategic coupling (Q10) is closed by docs/principles.md authoring.
- v2.0.0: §5 cross-model audit shared failure modes (Q9) is closed by external human audit (gate criteria authored at docs/v2_gate.md §2.1).
- v2.0.0: §10 NAMING.md FileRouter calibration (NEW): NAMING.md (~12 KB of markdown prose with comma-laden lines) is mis-routed by FileRouter's magic-byte sniff as CSV, producing 126 false-positive CSV findings (csv_comment_row, csv_inconsistent_columns, csv_formula_injection on bullet lines starting with '=', csv_column_type_drift, csv_encoding_divergence on UTF-8 arrows). Caught by the v2.0.0 recursive self-verification harness at tests/recursive_self_verification/test_self_scan.py. Calibration target: Round 21 FileRouter extension-vs-magic-byte reconciliation for .md files. Structural defense pending fix: TestPendingCalibrationDiagnostic::test_pending_doc_currently_produces_findings asserts the doc currently fires findings; when the FileRouter is calibrated and the doc scans clean, the diagnostic fails and forces re-promotion to _TOP_LEVEL_DOCS.
- v3.0+: §7 format-coverage holes (audio/video signal-level) open per ROADMAP_TO_V5.
- v4.0+: source-code substrate concealment per furqan-lint companion provisional.

## §12 Closing

This document does not retire any limitation; it publishes the shape of what Bayyinah cannot see. The Q1 thesis: honest publication of the blind spot is harder to attack than claimed completeness.

> Subhanaka, la 'ilma lana illa ma 'allamtana.
> Exalted are You; we have no knowledge except what You have taught us.
> Indeed, it is You who is the Knowing, the Wise.
> al-Baqarah 2:32

La hawla wa la quwwata illa billah.
