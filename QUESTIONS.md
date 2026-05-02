# Open Questions

A live list of interpretive questions about Bayyinah's own design that the project has not yet resolved. Publishing it is the recursive application of the project's thesis: a tool that detects performed alignment in other artifacts has to surface the gap between its own surface claims and its own substrate, or the tool is itself performing alignment.

This file is appended to, not rewritten. Questions move to a "Resolved" section with the version that resolved them. Questions are not bugs — they are interpretive issues whose right answer is not yet obvious.

## Maintainer

Bilal Syed Arfeen, project lead.

## Acknowledgement

This file was prompted by an external audit from Fraz Ashraf in May 2026. Several of the open questions below restate findings from that audit verbatim. The audit applied Bayyinah's own thesis to Bayyinah and found gaps the project had not surfaced internally; the appropriate response is to surface them publicly rather than absorb them silently.

## Open

### Q1. What is the adversarial document the score function cannot detect?

The integrity score is `clamp(1.0 - sum(severity * confidence), 0, 1)`. The score function is monotonic in finding count and severity but does not encode coverage. The honest claim is that the score is meaningful only when no concealment shape escaped the analyzer pipeline. Q1 is to construct, document, and publish in `KNOWN_LIMITS.md` a single adversarial document that scores 1.0 on the default pipeline despite carrying concealed payload, with the construction method.

This is the project's strongest possible affirmation of its own thesis. A scanner that publishes the shape of the input it cannot see is harder to attack than one that claims completeness.

### Q2. Is the parity-with-v0 invariant load-bearing or contingent?

`bayyinah.scan_pdf == bayyinah_v0.scan_pdf` on every Phase 0 fixture is asserted as a structural-honesty guarantee. It is also a guarantee that every defect in v0 ships forever, because fixing it breaks the invariant. The parity policy is being made conditional in this release (see `PARITY.md`) but the deeper question remains: at what threshold does v0's correctness become more important than reproduction of v0's behavior?

### Q3. The score function collapses heterogeneous risk

A document with five findings and a document with fifty findings both clamp to 0.0. For triage at scale this loses information; for compliance gates it loses more. Q3 is whether the score should remain continuous-and-saturating (current shape) or split into a continuous score plus a separate finding-count and coverage axis, and what the migration path is for downstream consumers who pin to the current shape.

### Q4. The `0.5` clamp lives inside a continuous distribution

A score of `0.5` in a CI dashboard is ambiguous: half-dirty file, or unscanned? `scan_incomplete=True` exists to disambiguate but the score channel re-introduces the type confusion the flag exists to prevent. v1.2 adds `scan_complete: bool` and a `coverage` field to the report; whether the score itself should be `null` when incomplete (rather than clamped to 0.5) remains open.

### Q5. The default pipeline silently lacks documented capabilities

Cross-modal correlation (subtitle/audio/metadata divergence) is listed as a supported mechanism but is opt-in and not wired into `ScanService().scan(path)` by default. The README and the report header now disclose this in v1.2; the question is whether default-off is the right policy long-term or whether v1.3 should make cross-modal default-on once the rule set stabilizes. Default-off preserves backward compatibility; default-on matches what the README's mechanism table implies.

### Q6. The parser is the attack surface

`pymupdf` and `pypdf` have shipped CVEs. A malicious PDF crafted to exploit the parser is the threat model of a hosted scan endpoint at bayyinah.dev. The current cloud deployment has a 25 MiB upload cap and a 256 MB library ceiling but no wall-clock timeout, no CPU-time limit, no process isolation, no seccomp/landlock posture, no description of what happens when `pymupdf` segfaults mid-parse. Q6 is whether v1.2's threat model is the right one and what isolation primitives the v1.3 cloud deployment commits to.

### Q7. The demo counter is obfuscated, not anonymized

SHA-256 of IPv4 over a daily-rotating salt is brute-forceable by enumeration in seconds on commodity hardware once the salt is known. The README's claim that "cross-day correlation is impossible without the per-instance secret" is true only as long as the secret is never logged, leaked, or rotated in a way that retains the prior value. v1.2 corrects the language to "obfuscated, not anonymized." The structural fix is HyperLogLog or a Bloom filter — counts without identifiers — and is committed for v1.2. Q7 stays open until that lands.

### Q8. Test count is not test quality

1,782 tests is the published number. The taxonomy is fixture-pinning plus integration. Missing from the suite: mutation testing (do the tests fail when an analyzer is broken?), differential testing against `pdfid`, `oletools`, `yara`, `clamav` on a shared corpus, adversarial fuzzing of the `FileRouter` polyglot dispatch, property-based tests with Hypothesis on the score function (idempotence, monotonicity in finding severity). The two-witnesses principle the README invokes (Al-Baqarah 2:282) is currently witnessed only by the project's own fixtures. Q8 is which of these external witness layers gets prioritized for v1.3.

### Q9. The cross-model audit shares failure modes

"Eight sessions, eight closing audits, zero open findings under the Munafiq Protocol cross-verification across three AI collaborators (Anthropic Claude, xAI Grok, Perplexity Computer)." Current LLMs share substantial failure modes (sycophancy, anchoring on prompt framing, agreement under social pressure). Three of them auditing the same artifact under the same framework reduces single-model variance but does not address shared bias. Q9 is whether the project should claim "audit-cleanness" at all in the absence of a human audit by someone paid to find holes, who does not accept the framework's premises.

### Q10. Strategic coupling of framework and engineering

The Quranic-principles section is load-bearing in the README. For Apache-2.0 OSS aiming at adoption in security teams, regulated industries, and academic citation, this couples adoption to acceptance of the framework. The engineering principles (deterministic byte-level checks, fail-closed defaults, additive-only invariants, fixture-pinned tests) stand without the framework — the framework explains *why* these principles were chosen, not *whether* they hold. Q10 is whether a framework-free statement of the engineering principles should appear somewhere in `docs/`, alongside the framework-anchored README, for readers whose adoption is gated on it.

This is not a question about removing the framework. It is a question about whether the project's adoption ceiling is the framework's audience, and whether that is the intended ceiling.

## Resolved

(Empty. Resolved questions are appended here with the version that closed them.)
