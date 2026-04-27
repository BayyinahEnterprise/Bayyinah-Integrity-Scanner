# ADR-001 - v1.2 Scope: Depth Before Breadth

**Status:** Accepted, 2026-04-26
**Author:** Bilal Syed Arfeen
**Reviewer:** Claude (Anthropic) - flagged the depth-vs-scope conflict in the superseded memo, this ADR is the response.
**Supersedes:** `docs/scope/file_type_coverage_v1_2.md` (kept as appendix; do not implement as written).

---

## Context

44 days remain to the Perplexity Billion Dollar Build competition (June 9, 2026). v1.1.1 is live at `bayyinah.dev`. The honest adversarial baseline at `docs/adversarial/REPORT.md` shows v1.1.1 fully recovers payloads on **2 of 42** adversarial fixtures, surfaces structural anomalies on a further **2**, and misses **38**. The PDF analyzer is the only one with full catches. DOCX, XLSX, HTML, EML score `1.000` average - every adversarial fixture in those formats currently passes through clean.

A scope-expansion memo was drafted that proposed adding 19 new FileKinds (`ODF*`, `DOCM/XLSM/PPTM`, `RTF`, `IPYNB`, `IMAGE_GIF/WEBP/BMP/TIFF/HEIC/ICO`, `DOC/XLS/PPT`, `MSG`, `EPUB`) plus another tier of stretch formats. Combined honest budget including fixtures: ~7,000-9,000 LOC across 4-5 weeks of build time.

Claude correctly identified two conflicts:

1. **The memo silently overrode the depth-before-scope rule** from feedback five days earlier. That rule said: do not expand scope until the existing 19 FileKinds are honest against the 42-fixture gauntlet.
2. **The memo's framing implies breadth wins the competition.** The thesis paper, the seven proofs, and the entire `docs/adversarial/REPORT.md` "publish what we miss" stance argue for depth. A v1.2 that ships breadth-without-depth would directly contradict our own published artifacts.

## Decision

The win condition for June 9 is **depth**: "Bayyinah catches what others miss." Not "Bayyinah supports more file types than others."

**v1.1.2 ships first** and closes the existing 42-fixture gauntlet across the 7 already-supported format families. This is the work already specced in `docs/adversarial/REPORT.md` § "v1.1.2 Milestone". Approximately 1,120 LOC across 42 new or extended mechanisms, every one traceable back to a concrete adversarial fixture published in this corpus. No speculative additions.

**v1.2.0 is the smallest defensible expansion** that aligns with the thesis:

- **CC-1** - `mughlaq` (closed) verdict rendering. Renders every out-of-scope or unknown-format result as a deliberate scope boundary instead of a confused 0.5. Includes a small backend change to return a structured `out_of_scope_reason` so the UI can render "here's what we'd look for if we supported this." ~200 LOC end-to-end, no analyzer risk.
- **A-3** - RTF analyzer. ~600 LOC + ~600 LOC of fixtures. Reason: RTF is the textbook concealment vector. Reviewers from the security community will specifically test it. Not covering RTF is a credibility gap that no amount of breadth elsewhere compensates for.
- **A-4** - Jupyter notebook (`.ipynb`) analyzer. ~400 LOC + ~600 LOC of fixtures. Reason: this is the **only** new analyzer that is the Bayyinah thesis as a demo - catching prompt injection hidden in cells that an LLM would load and execute. For the Perplexity audience specifically, this is the analyzer that gets remembered.

**v1.2.1 and beyond - explicitly deferred:** OpenDocument family, macro-enabled OOXML, image-family expansion, old binary Office, Outlook MSG, EPUB, raw archives, top-level XML, YAML/TOML/INI, calendar, columnar data, SQLite. All of these get a clean `mughlaq` verdict via CC-1 in the meantime. Each is documented in `docs/SCOPE.md` with rationale for the deferral.

## Consequences

### What we gain

- **The thesis paper, the seven proofs, the public adversarial report, and the v1.2.0 release notes all tell one story.** Depth. We publish what we miss, then close it.
- **A demo story that survives a hostile question.** "Why don't you support `.heic`?" → "Out of scope by policy for v1.2; here's what we would scan if we did. We chose to invest the engineering hours into closing 38 of 42 adversarial misses on the formats we already claim, instead of spreading thin." That is a stronger answer than any 50-FileKind boast.
- **Honest fixture engineering.** ~1,120 LOC of v1.1.2 mechanism code paired with the 42 existing fixtures, plus ~1,000 LOC of analyzer + ~1,200 LOC of fixtures for v1.2.0. Total honest budget: ~3,300 LOC across 6 weeks. Comfortable margin for the unforeseen.
- **CC-1 protects every deferred format from looking like a bug.** A judge dropping `.webp`, `.heic`, `.odt`, `.docm`, `.gif`, or anything else gets a clean closed-verdict panel with explanatory copy.

### What we give up

- **The "we cover more than anyone" pitch.** That was never our pitch. The memo briefly tempted it; this ADR refuses.
- **Any defense against a judge who specifically pulls a `.heic` from their phone** and wants to see real findings, not a `mughlaq`. Mitigation: CC-1's copy makes the deferral feel deliberate. Extra mitigation: the demo script encourages judges to drop a PDF or DOCX first (formats where we have v1.1.2's hardened detection), then offer to walk through the closed-verdict for any other format.
- **A future v1.3 with twelve more analyzers cannot be promised inside the competition window.** It can be promised on the roadmap.

### Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| v1.1.2 mechanisms regress an existing PDF catch | Medium | High | Run full 42-fixture gauntlet on every commit. Fail CI on any regression. |
| RTF analyzer hits a parser-grammar surprise | Low | Medium | RTF is fully specified by Microsoft. Pure-Python tokenizer, no third-party parser dependency. |
| Jupyter analyzer false-positives on legitimate hidden cells | Medium | Medium | Tier-2 finding, not Tier-1. Notebook authors legitimately collapse cells; the finding is structural ("a cell is hidden"), not interpretive ("this hidden cell is malicious"). |
| Time slips and v1.2.0 cannot ship by June 7 | Medium | High | v1.2.0 modularizes cleanly. CC-1 alone is shippable. RTF alone is shippable. Jupyter alone is shippable. Each lands as an atomic commit. Worst case: v1.2.0 ships with CC-1 only, v1.2.1 ships RTF, v1.2.2 ships Jupyter, all before June 7. |
| Judge specifically pulls an out-of-scope file and pushes back on `mughlaq` | High | Low | CC-1 copy + the depth answer above. Treat it as an opportunity to explain the thesis, not a problem to deflect. |

## Sequencing

**Tonight (April 26):** ship CC-1.

**Week 1 (April 27 - May 3):** v1.1.2 PDF + DOCX + XLSX gauntlet closure. Approximately 545 LOC (155 PDF + 200 DOCX + 190 XLSX). Run full gauntlet on each commit.

**Week 2 (May 4 - May 10):** v1.1.2 HTML + EML + Image + CSV/JSON gauntlet closure. Approximately 575 LOC. v1.1.2 release candidate end of week.

**Week 3 (May 11 - May 17):** v1.1.2 hardening + adversarial report rerun + Zenodo DOI mint. Tag v1.1.2.0. Begin RTF analyzer (A-3).

**Week 4 (May 18 - May 24):** Finish RTF analyzer + RTF fixture set. Begin Jupyter analyzer (A-4).

**Week 5 (May 25 - May 31):** Finish Jupyter analyzer + Jupyter fixture set. Run combined gauntlet across all 9 format families. Update `docs/adversarial/REPORT.md` with v1.2 numbers.

**Week 6 (June 1 - June 8):** Bug fix only. Tag v1.2.0 by June 7. Two days reserved for the unforeseen.

**June 9: competition.**

If a week slips: cut RTF or Jupyter. CC-1 + v1.1.2 alone is a defensible v1.2.0 release.

## Constraints (carried forward from the original memo, unchanged)

- Tier discipline (Tier-1 verified / Tier-2 structural / Tier-3 interpretive) on every new mechanism.
- Munafiq Protocol: every Tier-1 finding has a deterministic test in `tests/`.
- Falsifiability: every Tier-1 finding reproducible from a published fixture in `tests/fixtures/`.
- Zero em-dashes in user-facing prose. CSS comments and JS code comments exempt. READMEs ARE user-facing and count.
- Honest baseline: every miss documented in `docs/adversarial/REPORT.md`. If an analyzer doesn't catch something we expected it to, that's a fixture in the gauntlet, not silently dropped.
- Optional dependencies in `pyproject.toml` `[project.optional-dependencies]`.
- One commit per analyzer + its router changes + its tests + its fixture set. Atomic.

## What "done" looks like

1. v1.1.2 closes 38 of 42 existing adversarial misses (target: 38+ caught of 42).
2. v1.2.0 adds RTF and Jupyter with 6+ Tier-1 mechanisms each, paired clean+adversarial fixtures, full gauntlet pass.
3. CC-1 renders `mughlaq` cleanly for every out-of-scope or unknown-format file at `bayyinah.dev/`.
4. `docs/SCOPE.md` lists every supported and deliberately-deferred format with rationale.
5. `docs/adversarial/REPORT.md` shows v1.2.0 vs v1.1.1 numbers honestly.
6. The landing page's "23 file kinds" is updated truthfully (likely 21 or 22 with RTF + Jupyter; the memo's "50 file kinds" claim is abandoned).
7. Tag `v1.2.0` cut by June 7, 2026.

## What this ADR rejects

- The original `file_type_coverage_v1_2.md` memo's Tier A as written.
- Adding ODF, macro-OOXML, image-family expansion, MSG, EPUB before v1.1.2 lands.
- Any framing that sells breadth as the win condition for June 9.
- Implicit overrides of prior feedback. If a future memo proposes scope changes, it must explicitly cite and revisit prior commitments rather than silently superseding them.

---

*Bismillah. Depth. Then breadth, after.*
